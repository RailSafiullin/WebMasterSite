import asyncio
from datetime import datetime
from psycopg2 import IntegrityError
import requests
from sqlalchemy import select
from urllib.parse import unquote
from api.actions.actions import add_last_load_date
from db.models import LastUpdateDate, Url
from db.models import Metrics
from api.actions.urls import _add_new_urls
from api.actions.metrics_url import _add_new_metrics
from db.session import connect_db
from db.utils import get_last_update_date

from api.actions.actions import add_last_load_date

from fastapi import HTTPException

from const import date_format

async def add_data(data, last_update_date, async_session, mx_date=None):
    metrics = []  # Для пакетной вставки всех метрик
    # Собираем все URL из данных
    query_names = [unquote(query['text_indicator']['value']) for query in data['text_indicator_to_statistics']]

    # Извлекаем существующие URL за один запрос
    async with async_session() as session:
        existing_urls = await session.execute(
            select(Url).filter(Url.url.in_(query_names))
        )
        existing_urls = existing_urls.scalars().all()

    # Создаём словарь существующих URL {query_name: url_id}
    existing_url_ids = {url.url: url.id for url in existing_urls}

    # Собираем URL, которых нет в базе
    new_urls = []
    for query_name in query_names:
        if query_name not in existing_url_ids:
            new_urls.append(Url(url=query_name))

    # Вставляем новые URL в базу за один раз и обновляем словарь
    if new_urls:
        async with async_session() as session:
            session.add_all(new_urls)
            await session.commit()

    # Обновляем словарь с ID новыми URL
    for new_url in new_urls:
        existing_url_ids[new_url.url] = new_url.id
        
    async def process_query(query):
        query_name = unquote(query['text_indicator']['value'])

        # Обработка метрик для каждой статистики
        date = query['statistics'][0]["date"]
        data_add = {
            "date": date,
            "ctr": 0,
            "position": 0,
            "impression": 0,
            "demand": 0,
            "clicks": 0,
        }

        element_count = len(query['statistics'])

        for count, el in enumerate(query['statistics']):

            # Словарь для сопоставления поля с ключом в data_add
            field_mapping = {
                "IMPRESSIONS": "impression",
                "CLICKS": "clicks",
                "DEMAND": "demand",
                "CTR": "ctr",
                "POSITION": "position"
            }

            if date != el['date']:
                date = datetime.strptime(date, date_format)
                if mx_date:
                    mx_date[0] = max(mx_date[0], date)
                if date > last_update_date:
                    metrics.append(Metrics(
                        url_id=existing_url_ids[query_name],  # Используем url_id вместо url
                        date=date,
                        ctr=data_add['ctr'],
                        position=data_add['position'],
                        impression=data_add['impression'],
                        demand=data_add['demand'],
                        clicks=data_add['clicks']
                    ))
                date = el['date']
                data_add = {
                    "date": date,
                    "ctr": 0,
                    "position": 0,
                    "impression": 0,
                    "demand": 0,
                    "clicks": 0,
                }
            if count == element_count-1:
                # Обновление полей метрик
                field = el["field"]
                if field in field_mapping:
                    data_add[field_mapping[field]] = el["value"]
                date = datetime.strptime(date, date_format)
                if mx_date:
                    mx_date[0] = max(mx_date[0], date)
                if date > last_update_date:
                    metrics.append(Metrics(
                        url_id=existing_url_ids[query_name],  # Используем url_id вместо url
                        date=date,
                        ctr=data_add['ctr'],
                        position=data_add['position'],
                        impression=data_add['impression'],
                        demand=data_add['demand'],
                        clicks=data_add['clicks']
                    ))
                date = el['date']

            field = el["field"]
            if field in field_mapping:
                data_add[field_mapping[field]] = el["value"]


    # Создание списка задач для параллельной обработки каждого запроса
    tasks = [process_query(query) for query in data['text_indicator_to_statistics']]
    
    # Параллельное выполнение задач
    await asyncio.gather(*tasks)

    # Пакетная вставка всех метрик в базу данных
    if metrics:
        await _add_new_metrics(metrics, async_session)

async def get_data_by_page(page, last_update_date, URL, ACCESS_TOKEN, async_session):
    body = {
        "offset": page,
        "limit": 500,
        "device_type_indicator": "ALL",
        "text_indicator": "URL",
        "region_ids": [],
        "filters": {}
    }

    response = requests.post(URL, json=body, headers={'Authorization': f'OAuth {ACCESS_TOKEN}',
                                                      "Content-Type": "application/json; charset=UTF-8"})

    # print(response.text[:100])
    data = response.json()

    await add_data(data, last_update_date, async_session)

async def load_urls(config, group):
    DATABASE_NAME, ACCESS_TOKEN, USER_ID, HOST_ID, group = (config['database_name'],
                                                            config['access_token'],
                                                            config['user_id'],
                                                            config['host_id'],
                                                            group['name'])

    async_session = await connect_db(DATABASE_NAME)

    await add_last_load_date(async_session, "url")

    # Формируем URL для запроса мониторинга поисковых запросов
    URL = f"https://api.webmaster.yandex.net/v4/user/{USER_ID}/hosts/{HOST_ID}/query-analytics/list"

    # async_session = await create_db(DATABASE_NAME)
    body = {
        "offset": 0,
        "limit": 500,
        "device_type_indicator": "ALL",
        "text_indicator": "URL",
        "region_ids": [],
        "filters": {}
    }

    response = requests.post(URL, json=body, headers={'Authorization': f'OAuth {ACCESS_TOKEN}',
                                                      "Content-Type": "application/json; charset=UTF-8"})

    data = response.json()
    count = data["count"]
    last_update_date = await get_last_update_date(async_session, Metrics)
    print("last update date:", last_update_date)
    if not last_update_date:
        last_update_date = datetime.strptime("1900-01-01", date_format)
    mx_date = [datetime.strptime("1900-01-01", date_format)]
    query_count = 0
    try:
        await add_data(data, last_update_date, async_session, mx_date)
        query_count += 500
    except Exception as e:
        print("Error: ", e)
    print(mx_date, last_update_date)
    if mx_date[0] <= last_update_date:
        return {"status": 400,
                "detail": "Data is not up-to-date. Please refresh data before executing the script."
                }
    for offset in range(500, count, 500):
        print(f"[INFO] PAGE{offset} DONE!")
        curr = datetime.now()
        try:
            await get_data_by_page(offset, last_update_date, URL, ACCESS_TOKEN, async_session)
            query_count += 500
        except Exception as e:
            print("Error: ", e)
        print(datetime.now() - curr)

    return {"status": 200,
            "message": f"load {query_count} records"
            }



async def get_all_data(request_session):
    config, group = request_session["config"], request_session["group"]
    return await load_urls(config, group)

if __name__ == '__main__':
    cfg = {
        "database_name": "ayshotel",
        "access_token": "y0_AgAAAAANVf3MAAv6lgAAAAEIBw3PAADOvzU1b_RIdY0Wpw3RbuR6PgN7Cw",
        "user_id": "223739340",
        "host_id": "https:ayshotel.ru:443",
        "user": "admin"
    }
    asyncio.run(get_all_data(cfg))

