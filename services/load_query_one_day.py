import config
import asyncio
from datetime import datetime
from datetime import timedelta
import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from db.models import Query
from db.models import MetricsQuery
from db.session import async_session
from api.actions.queries import _add_new_urls
from api.actions.metrics_queries import _add_new_metrics, _delete_data

ACCESS_TOKEN = f"{config.ACCESS_TOKEN}"
USER_ID = f"{config.USER_ID}"
HOST_ID = f"{config.HOST_ID}"

date_format = "%Y-%m-%d"

# Формируем URL для запроса мониторинга поисковых запросов
URL = f"https://api.webmaster.yandex.net/v4/user/{USER_ID}/hosts/{HOST_ID}/query-analytics/list"


async def add_data(data, date):
    for query in data['text_indicator_to_statistics']:
        query_name = query['text_indicator']['value']
    
        try:
            async with async_session() as session:
                existing_query = await session.execute(
                    select(Query).filter_by(query=query_name)
                )
                existing_query = existing_query.scalar_one_or_none()
                
                if not existing_query:
                    # Если Query не существует, создаём новую запись
                    new_query = Query(query=query_name)
                    session.add(new_query)
                    await session.commit()
                    query_id = new_query.id
                else:
                    query_id = existing_query.id
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
        metrics.append(MetricsQuery(
            query_id=query_id,
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
        "text_indicator": "QUERY",
        "region_ids": [],
        "filters": {}
    }

    response = requests.post(URL, json=body, headers={'Authorization': f'OAuth {ACCESS_TOKEN}',
                                                      "Content-Type": "application/json; charset=UTF-8"})

    print(response.text[:100])
    data = response.json()

    await add_data(data, date)


async def get_all_data():
    date = (datetime.now() - timedelta(days=3))
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
        "text_indicator": "QUERY",
        "region_ids": [],
        "filters": {}
    }

    response = requests.post(URL, json=body, headers={'Authorization': f'OAuth {ACCESS_TOKEN}',
                                                      "Content-Type": "application/json; charset=UTF-8"})

    data = response.json()
    count = data["count"]
    await add_data(data, date)
    for offset in range(500, count, 500):
        print(f"[INFO] PAGE{offset} DONE!")
        await get_data_by_page(offset, date)


if __name__ == '__main__':
    asyncio.run(get_all_data())
