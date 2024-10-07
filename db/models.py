from datetime import datetime
from sqlalchemy import Float, Enum, ARRAY
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import DateTime
from sqlalchemy.orm import declarative_base

##############################
# BLOCK WITH DATABASE MODELS #
##############################

Base = declarative_base()


class Url(Base):
    __tablename__ = "url"

    url = Column(String, nullable=False, unique=True, primary_key=True)


class Metrics(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False)
    date = Column(DateTime, nullable=False, default=datetime.now)
    position = Column(Float, nullable=False)
    ctr = Column(Float, nullable=False)
    impression = Column(Float, nullable=False)
    demand = Column(Float, nullable=False)
    clicks = Column(Float, nullable=False)


class Query(Base):
    __tablename__ = "query"

    query = Column(String, nullable=False, unique=True, primary_key=True)


class MetricsQuery(Base):
    __tablename__ = "metrics_query"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String, nullable=False)
    date = Column(DateTime, nullable=False, default=datetime.now)
    position = Column(Float, nullable=False)
    ctr = Column(Float, nullable=False)
    impression = Column(Float, nullable=False)
    demand = Column(Float, nullable=False)
    clicks = Column(Float, nullable=False)


class QueryIndicator(Base):
    __tablename__ = "query_indicator"

    id = Column(Integer, primary_key=True, autoincrement=True)
    indicator = Column(
        Enum("TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION", "AVG_CLICK_POSITION", "TOTAL_CTR", name="indicator"),
        nullable=False)
    value = Column(Float, nullable=False)
    date = Column(DateTime, nullable=False)


class QueryUrlsMerge(Base):
    __tablename__ = "query_urls_merge"

    id = Column(Integer, nullable=False, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False, primary_key=True)
    queries = Column(ARRAY(String))
    date = Column(DateTime, nullable=False)


class QueryUrlsMergeLogs(Base):
    __tablename__ = "query_urls_merge_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    update_date = Column(DateTime, nullable=False)


class QueryUrlTop(Base):
    __tablename__ = "query_url_top"

    id = Column(Integer, primary_key=True, autoincrement=True)
    top = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    position = Column(Float, nullable=False)
    clicks = Column(Float, nullable=False)
    impression = Column(Float, nullable=False)
    count = Column(Integer, nullable=False)
    date = Column(DateTime, nullable=False)


class LastUpdateDate(Base):
    __tablename__ = "last_update_date"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    metrics_type = Column(String, nullable=False)