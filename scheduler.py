from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pytz import timezone


import config

_db_url = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DATABASE_GENERAL_NAME}"

jobstores = {
    "sqlalchemy": SQLAlchemyJobStore(url=_db_url)
}

moscow_timezone = timezone("Europe/Moscow")


scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=moscow_timezone)