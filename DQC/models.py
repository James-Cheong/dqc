# coding: utf-8
from sqlalchemy import Column, DECIMAL, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import INTEGER, TINYINT
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
metadata = Base.metadata


class Event(Base):
    __tablename__ = 'events'

    rid = Column(String(45, 'utf8mb4_0900_as_cs'), primary_key=True)
    type = Column(String(128, 'utf8mb4_0900_as_cs'))
    etl_name = Column(String(128, 'utf8mb4_0900_as_cs'), nullable=False)
    opened_at = Column(DateTime, nullable=False)
    checking_period = Column(INTEGER(11), nullable=False)
    data_start_time = Column(DateTime, nullable=False)
    data_end_time = Column(DateTime, nullable=False)


class Result(Base):
    __tablename__ = 'result'

    id = Column(INTEGER(11), primary_key=True)
    event_id = Column(ForeignKey('events.rid'), nullable=False, index=True)
    licensee_id = Column(INTEGER(11))
    source = Column(String(45, 'utf8mb4_0900_as_cs'))
    table_name = Column(String(255, 'utf8mb4_0900_as_cs'))
    column_name = Column(String(45, 'utf8mb4_0900_as_cs'))
    count = Column(INTEGER(11))
    mean = Column(DECIMAL(50, 3))
    min = Column(DECIMAL(50, 3))
    max = Column(DECIMAL(50, 3))

    event = relationship('Event')


class Status(Base):
    __tablename__ = 'status'

    id = Column(INTEGER(11), primary_key=True)
    event_id = Column(ForeignKey('events.rid'), index=True)
    licensee_id = Column(INTEGER(11))
    type = Column(String(85, 'utf8mb4_0900_as_cs'))
    name = Column(String(128, 'utf8mb4_0900_as_cs'))
    is_match = Column(TINYINT(1))
    unmatched_count = Column(INTEGER(11))
    remark = Column(Text(collation='utf8mb4_0900_as_cs'))

    event = relationship('Event')
