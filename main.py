from datetime import datetime
import schedule
from DQC.connector import Connector, logger, logging, settings


def job():
    start = datetime.now()
    logging.info('====================================================================================================')
    logging.info('Job started')
    for etl in settings.checklist:
        connector = Connector(settings.__getattr__(etl))
        logging.debug(connector.rule_status)
        if connector.rule_status:
            try:
                logging.info(
                    '----------------------------------------------------------------------------------------------')
                logging.info(f'Checking {connector.name}...')
                connector.validate()
                for i in connector.checking_period:
                    uid = connector.event(i)
                    src_table_df, dst_table_df = connector.generate_df(i)
                    # licensee_mode
                    if connector.licensee_mode is True:
                        licensee_src_dfs, licensee_dst_dfs = connector.licensee_dfs_transform(src_table_df,
                                                                                              dst_table_df)
                        for licensee_src_df, licensee_dst_df in zip(licensee_src_dfs, licensee_dst_dfs):
                            connector.status(licensee_src_df, licensee_dst_df, uid)
                            if not licensee_src_df.empty:
                                connector.result(licensee_src_df, connector.src_db, connector.src_table, uid)
                            if not licensee_dst_df.empty:
                                connector.result(licensee_dst_df, connector.dst_db, connector.dst_table, uid)
                    # normal mode
                    src_unique_rows, dst_unique_rows = connector.status(src_table_df, dst_table_df, uid)
                    if src_unique_rows is not None or dst_unique_rows is not None:
                        connector.send_email(src_unique_rows, dst_unique_rows, uid, i)
                    if not src_table_df.empty:
                        connector.result(src_table_df, connector.src_db, connector.src_table, uid)
                    if not dst_table_df.empty:
                        connector.result(dst_table_df, connector.dst_db, connector.dst_table, uid)
                    connector.purge_data()
            except:
                logger.exception("Catch an exception.")
                raise
            finally:
                connector.close_session()

    end = datetime.now()
    logging.info(f'Job ended')
    logging.info(f'Total run time: {(end - start).total_seconds()}s')


if __name__ == '__main__':
    job()
    schedule.every(settings.FREQUENCY).hours.do(job)

    while True:
        schedule.run_pending()
