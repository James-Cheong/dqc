import sys
from time import process_time
from datetime import datetime, timedelta
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from sqlalchemy_utils.functions import create_database, database_exists
import pandas as pd
import uuid
import datacompy
import logging
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
from DQC.models import Result, Event, Status, metadata
from DQC.config import settings
from DQC.logger import logger


def measure(func):
    @wraps(func)
    def _time_it(*args, **kwargs):
        start = int(round(process_time() * 1000))
        try:
            return func(*args, **kwargs)
        finally:
            end_ = int(round(process_time() * 1000)) - start
            logging.debug(
                f"Execution time for function {func.__name__}: {end_ if end_ > 0 else 0} ms"
            )

    return _time_it


def render_template(**kwargs):
    """Sends an email using a template."""
    templateloader = FileSystemLoader(searchpath="./templates/")
    html_env = Environment(loader=templateloader)
    template = html_env.get_template('templates.html')
    return template.render(**kwargs)


pd.set_option('display.float_format', lambda x: '%.3f' % x)
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.width', 320)


class Connector:
    def __init__(self, etl):
        self.name = etl.name
        self.config_engine = create_engine(
            f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}/ds_dqc_{settings.MYSQL_ENV}")
        self.session = Session(self.config_engine)
        self.src_db = etl.src_db
        self.dst_db = etl.dst_db
        self.src_engine = create_engine(etl.src_connection_string, pool_pre_ping=True)
        self.dst_engine = create_engine(etl.dst_connection_string, pool_pre_ping=True)
        self.src_table = etl.src_table
        self.dst_table = etl.dst_table
        self.src_sql = etl.src_query
        self.dst_sql = etl.dst_query
        # the desired time range for data need to be checked
        self.checking_period = settings.checking_period if settings.checking_period else etl.checking_period
        self.rule_status = settings.rule_status if settings.rule_status is True else etl.rule_status
        self.licensee_mode = etl.licensee_mode
        # using today's 00:00:00 as cut off time
        self.cut_off = datetime.utcnow() - timedelta(hours=datetime.utcnow().hour, minutes=datetime.utcnow().minute,
                                                     seconds=datetime.utcnow().second,
                                                     microseconds=datetime.utcnow().microsecond)

    def validate(self):
        self.src_engine.connect()
        logging.info(f"{self.src_db} connected")
        self.dst_engine.connect()
        logging.info(f"{self.dst_db} connected")
        if settings.DEBUG is False:
            if not database_exists(self.config_engine.url):
                create_database(self.config_engine.url)
                logging.info(f'ds_dqc_{settings.MYSQL_ENV} created')
            metadata.create_all(self.config_engine)
            if self.src_sql.count('%s') % 2 != 0 or self.src_sql.count('?') % 2 != 0:
                raise Exception('src_sql where condition has error')

    def event(self, checking_period_):
        """
        :param checking_period_: select checking period
        :return uid: return the uuid for other function
        """
        if settings.DEBUG is False:
            dqc_type = f'{self.src_db}-{self.dst_db}'
            uid = uuid.uuid1().hex.upper()
            event = Event(rid=uid, type=dqc_type, etl_name=self.name, opened_at=datetime.utcnow(),
                          checking_period=checking_period_,
                          data_start_time=self.cut_off - timedelta(days=checking_period_), data_end_time=self.cut_off)
            self.session.add(event)
            self.session.commit()
            return uid

    @measure
    def generate_df(self, checking_period_):
        src_times = self.src_sql.count('%s') // 2 if '%s' in self.src_sql else self.src_sql.count('?') // 2
        src_params = ((self.cut_off - timedelta(days=checking_period_)), self.cut_off) * src_times
        dst_params = ((self.cut_off - timedelta(days=checking_period_)), self.cut_off)
        src_table_df = pd.read_sql_query(self.src_sql, self.src_engine, params=src_params)
        dst_table_df = pd.read_sql_query(self.dst_sql, self.dst_engine, params=dst_params)
        if 'licensee_id' in dst_table_df.columns:
            src_table_df = src_table_df.astype({'licensee_id': 'object'})
            dst_table_df = dst_table_df.astype({'licensee_id': 'object'})
        logging.debug(src_table_df)
        logging.debug(f'src_table_df: {sys.getsizeof(src_table_df)/1024/1024} MB')
        logging.debug(dst_table_df)
        logging.debug(f'dst_table_df: {sys.getsizeof(dst_table_df)/1024/1024} MB')
        return src_table_df, dst_table_df

    @staticmethod
    def licensee_dfs_transform(src_table_df, dst_table_df):
        licensee_ids = dst_table_df['licensee_id'].drop_duplicates().array
        licensee_src_dfs = [src_table_df.loc[src_table_df['licensee_id'] == licensee_id] for licensee_id in
                            licensee_ids]
        licensee_dst_dfs = [dst_table_df.loc[dst_table_df['licensee_id'] == licensee_id] for licensee_id in
                            licensee_ids]
        return licensee_src_dfs, licensee_dst_dfs

    @measure
    def status(self, src, dst, uid):
        dqc_type = f'{self.src_db}-{self.dst_db}'
        if src.empty and dst.empty:
            if settings.DEBUG is False:
                status_ = Status(event_id=uid,
                                 licensee_id=None if self.licensee_mode is False else dst['licensee_id'].iloc[0],
                                 type=dqc_type,
                                 name=self.dst_table,
                                 remark='no data')
                self.session.add(status_)
                self.session.commit()
            return None, None
        else:
            # src = src.rename(columns={f'{src.columns[-1]}': f'{dst.columns[-1]}'})
            compare = datacompy.Compare(src.copy(), dst.copy(), join_columns=dst.columns)
            if compare.matches():
                if settings.DEBUG is False:
                    status_ = Status(event_id=uid,
                                     licensee_id=None if self.licensee_mode is False else dst['licensee_id'].iloc[0],
                                     type=dqc_type,
                                     name=self.dst_table,
                                     is_match=True, unmatched_count=0,
                                     remark='data are matched')
                    self.session.add(status_)
                    self.session.commit()
                return None, None
            else:
                unmatched_count = len(compare.df1_unq_rows) + len(compare.df2_unq_rows)
                if compare.df1_unq_rows.empty:
                    logging.debug(compare.df2_unq_rows)
                    remark = 'source table missing data'
                elif compare.df2_unq_rows.empty:
                    logging.debug(compare.df1_unq_rows)
                    remark = 'dest table missing data'
                else:
                    logging.debug(compare.df1_unq_rows)
                    logging.debug(compare.df2_unq_rows)
                    remark = 'both source and dest tables have unique rows'
                if settings.DEBUG is False:
                    status_ = Status(event_id=uid,
                                     licensee_id=None if self.licensee_mode is False else dst['licensee_id'].iloc[0],
                                     type=dqc_type,
                                     name=self.name,
                                     is_match=False, unmatched_count=unmatched_count,
                                     remark=remark)
                    self.session.add(status_)
                    self.session.commit()
                return compare.df1_unq_rows, compare.df2_unq_rows

    @measure
    def result(self, df_, db, table, uid_):
        source_result = df_.describe().loc[['count', 'mean', 'min', 'max']]
        if settings.DEBUG is False:
            for col in source_result.columns:
                self.session.add(
                    Result(event_id=uid_,
                           licensee_id=None if self.licensee_mode is False else df_['licensee_id'].iloc[0], source=db,
                           table_name=table, column_name=col,
                           count=source_result.at['count', col],
                           mean=source_result.at['mean', col],
                           min=source_result.at['min', col],
                           max=source_result.at['max', col]))
                self.session.commit()

    def close_session(self):
        self.session.close()

    @measure
    def send_email(self, src_unique_rows, dst_unique_rows, uid, checking_period_):
        smtp_server = settings.email_host
        sender = 'dqc@datasolutions'
        receiver = settings.email_receiver
        smtp_port = 25
        src_unique_dict = src_unique_rows.to_dict('split') if not src_unique_rows.empty else None
        dst_unique_dict = dst_unique_rows.to_dict('split') if not dst_unique_rows.empty else None

        start_time = self.cut_off - timedelta(days=checking_period_)
        end_time = self.cut_off
        data = {'name': self.name, 'time': datetime.utcnow(), 'event_id': uid, 'src_query': self.src_sql,
                'dst_query': self.dst_sql,
                'start_time': start_time,
                'end_time': end_time,
                'src_unique_dict': src_unique_dict, 'dst_unique_dict': dst_unique_dict}
        msg = MIMEMultipart("alternative")
        msg['From'] = sender
        msg['To'] = ", ".join(receiver)
        msg['Subject'] = 'DQC - Found Unmatched Rows'
        body = render_template(**data)

        msg.attach(MIMEText(body, 'html'))
        if settings.DEBUG is False:
            server = smtplib.SMTP(smtp_server, smtp_port)
            try:
                server.sendmail(sender, receiver, msg.as_string())
                logging.info("Email Sent!")
            except smtplib.SMTPException:
                logger.exception("Error: fail to send email!")
            finally:
                server.quit()

    @measure
    def purge_data(self):
        if settings.DEBUG is False:
            ids = self.session.execute(
                select(Event.rid).where(Event.opened_at < self.cut_off - timedelta(days=settings.retention_period)))
            for row in ids.scalars().all():
                self.session.execute(delete(Result).where(Result.event_id == row))
                self.session.execute(delete(Status).where(Status.event_id == row))
                self.session.execute(delete(Event).where(Event.rid == row))
            self.session.commit()
