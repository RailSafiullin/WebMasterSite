import config
import asyncio
from datetime import datetime
import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from db.models import Url
from db.models import Metrics
from db.session import async_session
from api.actions.urls import _add_new_urls
from api.actions.metrics_url import _add_new_metrics, _delete_data

ACCESS_TOKEN = f"{config.ACCESS_TOKEN}"
USER_ID = f"{config.USER_ID}"
HOST_ID = f"{config.HOST_ID}"

date_format = "%Y-%m-%d"

# Формируем URL для запроса мониторинга поисковых запросов
URL = f"https://api.webmaster.yandex.net/v4/user/{USER_ID}/hosts/{HOST_ID}/query-analytics/list"


async def add_data(data, date):
    for query in data['text_indicator_to_statistics']:
        query_name = query['text_indicator']['value']

        url_id = (await async_session.execute(
            select(Url.id).where(Url.url == query_name)
        )).scalars().first()
        
        try:
            async with async_session() as session:
                existing_url = await session.execute(
                    select(Url).filter_by(url=query_name)
                )
                existing_url = existing_url.scalar_one_or_none()
                
                if not existing_url:
                    # Если Query не существует, создаём новую запись
                    new_query = Url(url=query_name)
                    session.add(new_query)
                    await session.commit()
                    url_id = new_query.id
                else:
                    url_id = existing_url.id
        except IntegrityError:
            pass
        metrics = []
        data_add = {
            "date": date,
            "ctr": 0,
            "position": 0,
            "impression": 0,
            "demand": 0,
            "clicks": 0,
        }
        for el in query['statistics']:
            if date == el['date']:
                field = el["field"]
                if field == "IMPRESSIONS":
                    data_add["impression"] = el["value"]
                elif field == "CLICKS":
                    data_add["clicks"] = el["value"]
                elif field == "DEMAND":
                    data_add["demand"] = el["value"]
                elif field == "CTR":
                    data_add["ctr"] = el["value"]
                elif field == "POSITION":
                    data_add["position"] = el["value"]
        metrics.append(Metrics(
            url_id=url_id,
            date=datetime.strptime(date, date_format),
            ctr=data_add['ctr'],
            position=data_add['position'],
            impression=data_add['impression'],
            demand=data_add['demand'],
            clicks=data_add['clicks']
        ))
        await _add_new_metrics(metrics, async_session)


async def get_data_by_page(page, date):
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

    print(response.text[:100])
    data = response.json()

    await add_data(data, date)


async def get_all_data():
    date_input = input("Введите дату, которую необходимо обновить (в формате YYYY-MM-DD): ")

    try:
        # Преобразование строки в объект даты
        date_obj = datetime.strptime(date_input, "%Y-%m-%d")
        print(f"Введенная дата: {date_obj}")
    except ValueError:
        print("Неверный формат даты. Пожалуйста, введите дату в формате YYYY-MM-DD.")
    await _delete_data(date_obj, async_session)
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
    await add_data(data, date_obj)
    for offset in range(500, count, 500):
        print(f"[INFO] PAGE{offset} DONE!")
        await get_data_by_page(offset, date_obj)


if __name__ == '__main__':
    asyncio.run(get_all_data())
