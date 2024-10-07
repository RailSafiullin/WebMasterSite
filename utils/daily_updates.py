import logging

from sqlalchemy import select
from services.load_all_urls import load_urls
from services.load_all_queries import load_queries
from services.load_all_history import load_history

from api.config.models import Config, Group
from db.session import async_session_general
from const import LOGGING_FORMAT, LOGGING_DATE_FORMAT

logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT, datefmt=LOGGING_DATE_FORMAT)
logger = logging.getLogger(name=f"{__name__}".upper())

async def is_update_available(config: Config, group: Group) -> bool:
    response = await load_queries(config.__dict__, group.__dict__)
    return response["status"] == 200


async def daily_updates(main_config_name: str, main_group_name: str):
    logger.info(f"Starting daily updates for main config: {main_config_name}")
    async with async_session_general() as session:
        config = (await session.execute(
            select(Config).where(Config.name == main_config_name)
        )).scalars().first()
        if config is None:
            logger.error(f"main config {main_config_name} not found, skipping daily updates")
            return
        group = (await session.execute(
            select(Group).where(Group.name == main_group_name))).scalars().first()
        if group is None:
            logger.error(f"main group {main_group_name} not found, skipping daily updates")
            return
        if not await is_update_available(config, group):
            logger.error(f"no updates available for main config: {config.name}, skipping daily updates")
            return
        configs = (await session.execute(
            select(Config).where(Config.name != main_config_name)
        )).scalars().all()
    group_dict = group.__dict__
    await load_urls(config.__dict__, group_dict)
    await load_history(config.__dict__, group_dict)
    for config in configs:
        config_dict = config.__dict__
        logger.info(f"Starting daily updates for config: {config.name}")
        if (await load_queries(config_dict, group_dict))["status"] != 200:
            logger.error(f"no query updates available for config: {config.name}")
        else:
            logger.info(f"queries updated for config: {config.name}")
        if (await load_urls(config_dict, group_dict))["status"] != 200:
            logger.error(f"no urls available for config: {config.name}")
        else:
            logger.info(f"urls updated for config: {config.name}")
        logger.info(f"loading history for config: {config.name}")
        await load_history(config_dict, group_dict)
