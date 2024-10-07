from sqlalchemy import select
from db.session import async_session_general
from services.load_all_urls import load_urls
from services.load_all_queries import load_queries
from services.load_all_history import load_history
from api.config.models import Config, Group


async def is_update_available(config: Config, group: Group) -> bool:
    response = await load_queries(config.__dict__, group.__dict__)
    return response["status"] == 200


async def daily_updates(main_config_name: str, main_group_name: str):
    async with async_session_general() as session:
        config = (await session.execute(
            select(Config).where(Config.name == main_config_name)
        )).scalars().first()
        if config is None:
            print("config not found")
            return
        group = (await session.execute(
            select(Group).where(Group.name == main_group_name))).scalars().first()
        if group is None:
            print("group not found")
            return
        if not await is_update_available(config, group):
            print("no updates for today")
            return
        configs = (await session.execute(
            select(Config).where(Config.name != main_config_name)
        )).scalars().all()
    group_dict = group.__dict__
    for config in configs:
        config_dict = config.__dict__
        await load_queries(config_dict, group_dict)
        await load_urls(config_dict, group_dict)
        await load_history(config_dict, group_dict)
