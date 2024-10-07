from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from pytz import timezone

from api.auth.models import Base
from api.config.models import AutoUpdatesMode
from api.config.utils import load_auto_updates_schedule, update_list
from db.session import async_session_general
from utils.daily_updates import daily_updates

import config

_db_url = f"postgresql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DATABASE_GENERAL_NAME}"

jobstores = {
    "sqlalchemy": SQLAlchemyJobStore(url=_db_url, metadata=Base.metadata)
}

moscow_timezone = timezone("Europe/Moscow")

scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=moscow_timezone)


async def prepare_scheduler():
    scheduler.start()
    async with async_session_general() as session:
        schedules = await load_auto_updates_schedule(session)
        for schedule, user in schedules:
            scheduler.add_job(update_list, id=str(schedule.id),
                args=(user, schedule.list_id),
                trigger=CronTrigger(
                    hour=schedule.hours,
                    minute=schedule.minutes,
                    day_of_week=schedule.days if schedule.mode == AutoUpdatesMode.WeekDays else None,
                    day=schedule.days if schedule.mode == AutoUpdatesMode.MonthDays else None,
                    timezone=scheduler.timezone
                )
            )
    scheduler.add_job(
        id="daily_updates",
        func=daily_updates,
        args=(config.DAILY_UPDATE_MAIN_CONFIG_NAME, config.DAILY_UPDATE_MAIN_GROUP_NAME),
        trigger=CronTrigger(
            hour=config.DAILY_UPDATE_HOURS,
            minute=config.DAILY_UPDATE_MINUTES,
            timezone=config.DAILY_UPDATE_TIME_ZONE,
        )
    )
