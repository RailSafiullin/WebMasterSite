import asyncio
from datetime import datetime, timedelta
from itertools import groupby

import requests

from api.actions.actions import add_last_load_date
from api.actions.indicators import _add_new_indicators, _add_top
from api.actions.metrics_queries import _get_top_data_query
from api.actions.metrics_url import _get_top_data_urls
from api.actions.top import get_last_date_update_for
from config import DB_HOST
from db.models import QueryIndicator, QueryUrlTop

from db.session import connect_db
from db.utils import get_last_update_date

date_format = "%Y-%m-%d"


def create_url(USER_ID, HOST_ID):
    date_to = datetime.now() - timedelta(days=2)
    date_to = date_to.date()
    date_from = date_to - timedelta(days=365)
    print(f"date_from: {date_from} date_to: {date_to}")
    return (f"https://api.webmaster.yandex.net/v4/user/{USER_ID}/hosts/{HOST_ID}/search-queries/all/history?"
            f"query_indicator=TOTAL_SHOWS&"
            f"query_indicator=TOTAL_CLICKS&"
            f"query_indicator=AVG_SHOW_POSITION&"
            f"query_indicator=AVG_CLICK_POSITION&"
            f"date_from={date_from}&"
            f"date_to={date_to}")


async def get_response(async_session, USER_ID, HOST_ID, ACCESS_TOKEN):
    print("Начало выгрузки")
    URL = create_url(USER_ID, HOST_ID)
    if URL == -1:
        return -1
    response = requests.get(URL, headers={'Authorization': f'OAuth {ACCESS_TOKEN}',
                                          "Content-Type": "application/json; charset=UTF-8"})

    return response


async def add_data(response: requests.models.Response, async_session):
    indicators = response.json()["indicators"]

    data_for_db = list()
    data_for_total_ctr = dict()
    for indicator in indicators:
        for element in indicators[indicator]:
            date = datetime.strptime(element["date"].split("T")[0], date_format)
            data_for_db.append(QueryIndicator(indicator=indicator,
                                              value=round(element["value"], 2),
                                              date=date))
            if date not in data_for_total_ctr:
                data_for_total_ctr[date] = [0, 0]
            if indicator == "TOTAL_CLICKS":
                data_for_total_ctr[date][0] = element["value"]
            elif indicator == "TOTAL_SHOWS":
                data_for_total_ctr[date][1] = element["value"]
    for key, value in data_for_total_ctr.items():
        value = round(value[0] * 100 / value[1], 2) if value[1] != 0 else 0
        data_for_db.append(QueryIndicator(
            indicator="TOTAL_CTR",
            value=value,
            date=key
        )
        )

    await _add_new_indicators(data_for_db, async_session)

    return data_for_db


async def add_top(async_session):
    last_update_date_query = await get_last_date_update_for(async_session, "query")
    print("last update date for query top 3, 5, 10, 20, 30:", last_update_date_query)

    top_position = 3, 5, 10, 20, 30
    add_values = []
    for top in top_position:
        queries_top = await _get_top_data_query(top, async_session)
        if queries_top:
            queries_top.sort(key=lambda x: x[-1])
        grouped_data = {k: list(v) for k, v in groupby(queries_top, key=lambda x: x[-1])}
        for key, value in grouped_data.items():
            if key > last_update_date_query:
                impression_sum = sum(x[0] for x in value)
                clicks_sum = sum(x[1] for x in value)
                position_sum = round(sum(x[2] for x in value) / len(value), 2)
                add_values.append(
                    QueryUrlTop(top=top, type="query", position=position_sum, clicks=clicks_sum,
                                impression=impression_sum, count=len(value),
                                date=key))

    last_update_date_url = await get_last_date_update_for(async_session, "url")
    print("last update date for query top 3, 5, 10, 20, 30:", last_update_date_url)

    top_position = 3, 5, 10, 20, 30
    for top in top_position:
        urls_top = await _get_top_data_urls(top, async_session)
        if urls_top:
            urls_top.sort(key=lambda x: x[-1])
        grouped_data = {k: list(v) for k, v in groupby(urls_top, key=lambda x: x[-1])}
        for key, value in grouped_data.items():
            if key > last_update_date_url:
                impression_sum = sum(x[0] for x in value)
                clicks_sum = sum(x[1] for x in value)
                position_sum = round(sum(x[2] for x in value) / len(value), 2)
                add_values.append(
                    QueryUrlTop(top=top, type="url", position=position_sum, clicks=clicks_sum,
                                impression=impression_sum, count=len(value),
                                date=key))

    await _add_top(add_values, async_session)


async def load_history(config, group):
    DATABASE_NAME, ACCESS_TOKEN, USER_ID, HOST_ID, group = (config['database_name'],
                                                            config['access_token'],
                                                            config['user_id'],
                                                            config['host_id'],
                                                            group['name'])
    async_session = await connect_db(DATABASE_NAME)

    await add_last_load_date(async_session, "history")

    response = await get_response(async_session, USER_ID, HOST_ID, ACCESS_TOKEN)
    await add_data(response, async_session)
    print("Indicators загружены. Начинаем загрузку TOP")
    await add_top(async_session)
    print("Выгрузка завершена")


async def main(request_session):
    config, group = request_session["config"], request_session["group"]
    return await load_history(config, group)

if __name__ == '__main__':
    asyncio.run(main())
