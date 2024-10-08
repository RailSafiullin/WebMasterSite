from datetime import datetime, timedelta
from typing import List

from fastapi import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import asc, case, select, distinct, delete, text
from sqlalchemy import and_
from sqlalchemy import desc, func, or_

from db.models import QueryIndicator, QueryUrlTop, QueryUrlsMerge, Url
from db.models import Metrics
from db.models import Query
from db.models import MetricsQuery
from db.utils import get_last_update_date

from api.config.models import List as List_model, ListURI

from const import date_format

###########################################################
# BLOCK FOR INTERACTION WITH DATABASE IN BUSINESS CONTEXT #
###########################################################


class UrlDAL:
    """Data Access Layer for operating user info"""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_new_urls(
            self,
            add_values
    ):
        for value in add_values:
            await self.db_session.merge(value)
        await self.db_session.flush()
        return

    async def get_urls_with_pagination(
            self, 
            page, 
            per_page, 
            date_start, 
            date_end, 
            state, 
            state_date, 
            metric_type, 
            state_type, 
            list_name,
            general_db
            ):
        
        filter_query = None
        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()
            
            #filter_query = Url.url.in_(uri_list)

            #filter_query_result = Metrics.url.in_(uri_list)

            url_id_list = (await general_db.execute(
                select(Url.id).where(Url.url.in_(uri_list)))).scalars().all()

            # Фильтрация по Url.id на основе uri_list
            if url_id_list:
                filter_query = Url.id.in_(url_id_list)
                filter_query_result = Metrics.url_id.in_(url_id_list)

        if metric_type == "P":
            pointer = Metrics.position
            result_pointer = func.avg(Metrics.position)
        if metric_type == "K":
            pointer = Metrics.clicks
            result_pointer = func.sum(Metrics.clicks)
        if metric_type == "R":
            pointer = Metrics.impression
            result_pointer = func.sum(Metrics.impression)
        if metric_type == "C":
            pointer = Metrics.ctr
            result_pointer = func.avg(Metrics.ctr)
        
        sub_query = select(Url)

        sub_query_result = select(Url).join(MetricsQuery, MetricsQuery.url_id == Url.id)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

            sub_query_result = sub_query_result.filter(filter_query_result)

        if not state:
            
            sub = sub_query.offset(page).limit(per_page).subquery()
            query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                        Metrics.ctr, sub.c.url).join(sub,
                                                    Metrics.url_id == sub.c.id).group_by(
                sub.c.id, sub.c.url,  
                Metrics.date,   
                Metrics.position,
                Metrics.clicks,
                Metrics.impression,
                Metrics.ctr,
            ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))

        elif state == "decrease":
            if state_type == "date":

                sub = sub_query_result.where(Metrics.date == state_date).group_by(Url.url, Url.id).order_by(desc(pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
            else:

                sub = sub_query_result.where(
                    and_(Metrics.date >= date_start, Metrics.date <= date_end)).group_by(Url.url, Url.id).order_by(
                    desc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        
        elif state == "increase":
            if pointer == Metrics.position:
                    pointer = case(
                        (pointer == 0, float('inf')),  # если pointer == 0, заменяем на float('inf')
                        else_=pointer  # иначе используем значение pointer
                    )
            if state_type == "date":

                sub = sub_query_result.where(Metrics.date == state_date).group_by(Url.url, Url.id).order_by(asc(pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
            else:

                sub = sub_query_result.where(
                    and_(Metrics.date >= date_start, Metrics.date <= date_end)).group_by(Url.url, Url.id).order_by(
                    asc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))

        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_and_like(
            self, 
            page, 
            per_page, 
            date_start, 
            date_end, 
            search_text, 
            state, 
            state_date, 
            metric_type, 
            state_type,
            list_name,
            general_db,
            ):
        
        filter_query = None


        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()
            
            #filter_query = Url.url.in_(uri_list)

            #filter_query_result = Metrics.url.in_(uri_list)

            url_id_list = (await general_db.execute(
                select(Url.id).where(Url.url.in_(uri_list)))).scalars().all()

            # Фильтрация по Url.id на основе uri_list
            if url_id_list:
                filter_query = Url.id.in_(url_id_list)
                filter_query_result = Metrics.url_id.in_(url_id_list)

        if metric_type == "P":
            pointer = Metrics.position
            result_pointer = func.avg(Metrics.position)
        if metric_type == "K":
            pointer = Metrics.clicks
            result_pointer = func.sum(Metrics.clicks)
        if metric_type == "R":
            pointer = Metrics.impression
            result_pointer = func.sum(Metrics.impression)
        if metric_type == "C":
            pointer = Metrics.ctr
            result_pointer = func.avg(Metrics.ctr)
        
        sub_query = select(Url)

        sub_query_result = select(Url).join(MetricsQuery, MetricsQuery.url_id == Url.id)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

            sub_query_result = sub_query_result.filter(filter_query_result)

        if not state:
            sub = sub_query.filter(Url.url.like(f"%{search_text.strip()}%")).offset(page).limit(
                per_page).subquery()
            query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                        Metrics.ctr, sub).join(sub,
                                                    Metrics.url_id == sub.c.id).group_by(
                sub.c.id, sub.c.url,
                Metrics.date,
                Metrics.position,
                Metrics.clicks,
                Metrics.impression,
                Metrics.ctr,
            ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))

        elif state == "decrease":
            if state_type == "date":
                
                sub = sub_query_result.filter(Url.url.like(f"%{search_text.strip()}%")).where(Metrics.date == state_date).group_by(Url.url, Url.id).order_by(desc(pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
            else:

                sub = sub_query_result.filter(Url.url.like(f"%{search_text.strip()}%")).where(
                    and_(Metrics.date >= date_start, Metrics.date <= date_end)).group_by(Url.url, Url.id).order_by(
                    desc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        
        elif state == "increase":
            if pointer == Metrics.position:
                    pointer = case(
                        (pointer == 0, float('inf')),  # если pointer == 0, заменяем на float('inf')
                        else_=pointer  # иначе используем значение pointer
                    )
            if state_type == "date":

                sub = sub_query_result.filter(Url.url.like(f"%{search_text.strip()}%")).where(Metrics.date == state_date).group_by(Url.url, Url.id).order_by(asc(pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
            else:

                sub = sub_query_result.filter(Url.url.like(f"%{search_text.strip()}%")).where(
                    and_(Metrics.date >= date_start, Metrics.date <= date_end)).group_by(Url.url, Url.id).order_by(
                    asc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression,
                            Metrics.ctr, sub.c.url).join(sub,
                                                        Metrics.url_id == sub.c.id).group_by(
                    sub.c.id, sub.c.url,
                    Metrics.date,
                    Metrics.position,
                    Metrics.clicks,
                    Metrics.impression,
                    Metrics.ctr,
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))

        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_sort(
            self, 
            page, 
            per_page, 
            date_start, 
            date_end, 
            sort_desc,
            list_name,
            general_db,
            ):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()
            
            #filter_query = Url.url.in_(uri_list)
            url_id_list = (await general_db.execute(
                select(Url.id).where(Url.url.in_(uri_list)))).scalars().all()

            # Фильтрация по Url.id на основе uri_list
            if url_id_list:
                filter_query = Url.id.in_(url_id_list)

        
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)
            
        if sort_desc:
            sub = sub_query.order_by(desc(Url.url)).offset(page).limit(
                per_page).subquery()
        else:
            sub = sub_query.order_by(Url.url).offset(page).limit(
                per_page).subquery()
        query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression, Metrics.ctr, sub.c.url).join(sub,
                                                                                                                  Metrics.url_id == sub.c.id).group_by(
            sub.c.id, sub.c.url,
            Metrics.date,
            Metrics.position,
            Metrics.clicks,
            Metrics.impression,
            Metrics.ctr,
        ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_and_like_sort(
            self, 
            page, 
            per_page, 
            date_start, 
            date_end, 
            search_text,
            sort_desc,
            list_name,
            general_db,
            ):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()

            filter_query = Url.url.in_(uri_list)
        
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

        if sort_desc:
            sub = sub_query.filter(Url.url.like(f"%{search_text.strip()}%")).order_by(desc(Url.url)).offset(
                page).limit(per_page).subquery()
        else:
            sub = sub_query.filter(Url.url.like(f"%{search_text.strip()}%")).order_by(Url.url).offset(page).limit(
                per_page).subquery()
        query = select(Metrics.date, Metrics.position, Metrics.clicks, Metrics.impression, Metrics.ctr, sub.c.url).join(sub,
                                                                                                                  Metrics.url_id == sub.c.id).group_by(
            sub.c.id, sub.c.url,
            Metrics.date,
            Metrics.position,
            Metrics.clicks,
            Metrics.impression,
            Metrics.ctr,
        ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row
        
    async def get_metrics_daily_summary_like(self, date_start, date_end, search_text, list_name, general_db):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()

            filter_query = Url.url.in_(uri_list)
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

        sub = sub_query.filter(Url.url.like(f"%{search_text.strip()}%")).subquery()
        query = select(Metrics.date, Metrics.clicks, Metrics.impression
                    ).join(sub, Metrics.url_id == sub.c.id
                    ).group_by(Metrics.date,
                    ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        
        query = select(Metrics.date, 
                    func.sum(Metrics.clicks).label('total_clicks'),
                    func.sum(Metrics.impression).label('total_impressions'),
                    
                    ).join(sub, Metrics.url_id == sub.c.id
                    ).group_by(Metrics.date,
                    ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start))
        
        res = await self.db_session.execute(query)
        
        product_row = res.fetchall()
        
        query = select(func.count()).filter(Url.url.like(f"%{search_text.strip()}%")).limit(1)
        total_records = await self.db_session.execute(query)
        #return {"total_records": total_records, "data": product_row}
        if len(product_row) != 0:   
            return product_row, total_records.first()

    async def get_metrics_daily_summary(self, date_start, date_end, list_name, general_db):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()

            filter_query = Url.url.in_(uri_list)
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

        sub = sub_query.subquery()    

        query = select(Metrics.date, 
                    func.sum(Metrics.clicks).label('total_clicks'),
                    func.sum(Metrics.impression).label('total_impressions'),
                    ).join(sub, Metrics.url_id == sub.c.id
                    ).group_by(Metrics.date,
                    ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start)      
                )  
        
        res = await self.db_session.execute(query)
        product_row = res.fetchall()

        query = select(func.count()).select_from(sub).limit(1)
        total_records = await self.db_session.execute(query)
        if len(product_row) != 0:   
            return product_row, total_records.first()
        
    async def get_not_void_count_daily_summary_like(self, date_start, date_end, search_text, list_name, general_db):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()

            filter_query = Url.url.in_(uri_list)
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

        sub = sub_query.filter(Url.url.like(f"%{search_text.strip()}%")).subquery()

        sub_count_query = select(Metrics.date.label("date"), func.count().label("count_line")                
                ).join(sub, Metrics.url_id == sub.c.id
                ).where(Metrics.position > 0
                ).group_by(Metrics.date
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start)
                )
        res = await self.db_session.execute(sub_count_query)

        product_row = res.fetchall()
        
        if len(product_row) != 0:
            return product_row
        
    async def get_not_void_count_daily_summary(self, date_start, date_end, list_name, general_db):

        filter_query = None

        if list_name != "None":
            list_id = (await general_db.execute(
                select(List_model.id).where(List_model.name == list_name)
            )).fetchone()[0]

            uri_list = (await general_db.execute(
                select(ListURI.uri).where(ListURI.list_id == list_id)
            )).scalars().all()

            filter_query = Url.url.in_(uri_list)
        sub_query = select(Url)
            
        if filter_query is not None:
            sub_query = sub_query.filter(filter_query)

        sub = sub_query.subquery()    

        sub_count_query = select(Metrics.date.label("date"), func.count().label("count_line")                
                ).join(sub, Metrics.url_id == sub.c.id
                ).where(Metrics.position > 0
                ).group_by(Metrics.date
                ).having(and_(Metrics.date <= date_end, Metrics.date >= date_start)
                )
        res = await self.db_session.execute(sub_count_query)

        product_row = res.fetchall()
        
        if len(product_row) != 0:
            return product_row

class MetricDAL:
    """Data Access Layer for operating user info"""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_new_metrics(
            self,
            add_values
    ):
        self.db_session.add_all(add_values)
        await self.db_session.flush()
        return

    async def get_top_data(
            self,
            top: int
    ):
        query = select(Metrics.impression, Metrics.clicks, Metrics.position, Metrics.date).where(and_(
            Metrics.position <= top, Metrics.position > 0))
        result = await self.db_session.execute(query)
        return result.fetchall()

    async def delete_data(
            self,
            date
    ):
        query = delete(Metrics).where(Metrics.date == date)
        await self.db_session.execute(query)
        await self.db_session.commit()


class QueryDAL:
    """Data Access Layer for operating user info"""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_new_urls(
            self,
            add_values
    ):
        for value in add_values:
            await self.db_session.merge(value)
        await self.db_session.flush()
        return

    async def get_urls_with_pagination(self, page, per_page, date_start, date_end, state, state_date, metric_type, state_type):
        if metric_type == "P":
            pointer = MetricsQuery.position
            result_pointer = func.avg(MetricsQuery.position)
        if metric_type == "K":
            pointer = MetricsQuery.clicks
            result_pointer = func.sum(MetricsQuery.clicks)
        if metric_type == "R":
            pointer = MetricsQuery.impression
            result_pointer = func.sum(MetricsQuery.impression)
        if metric_type == "C":
            pointer = MetricsQuery.ctr
            result_pointer = func.avg(MetricsQuery.ctr)
        if not state:
            sub = select(Query).offset(page).limit(
                per_page).subquery()
            query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                        MetricsQuery.ctr, sub.c.query).join(sub,
                                                    MetricsQuery.query_id == sub.c.id).group_by(
                sub.c.id, sub.c.query,
                MetricsQuery.date,
                MetricsQuery.position,
                MetricsQuery.clicks,
                MetricsQuery.impression,
                MetricsQuery.ctr,
            ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))

        elif state == "decrease":
            if state_type == "date":
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).where(MetricsQuery.date == state_date).group_by(Query.query, Query.id).order_by(desc(pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
            else:
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).where(
                    and_(MetricsQuery.date >= date_start, MetricsQuery.date <= date_end)).group_by(Query.query, Query.id).order_by(
                    desc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        
        elif state == "increase":
            if state_type == "date":
                if pointer == MetricsQuery.position:
                    pointer = case(
                        (pointer == 0, float('inf')),  # если pointer == 0, заменяем на float('inf')
                        else_=pointer  # иначе используем значение pointer
                    )
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).where(MetricsQuery.date == state_date).group_by(Query.query, Query.id).order_by(asc(pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
            else:
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).where(
                    and_(MetricsQuery.date >= date_start, MetricsQuery.date <= date_end)).group_by(Query.query, Query.id).order_by(
                    asc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))

        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_and_like(self, page, per_page, date_start, date_end, search_text, state, state_date, metric_type, state_type):
        if metric_type == "P":
            pointer = MetricsQuery.position
            result_pointer = func.avg(MetricsQuery.position)
        if metric_type == "K":
            pointer = MetricsQuery.clicks
            result_pointer = func.sum(MetricsQuery.clicks)
        if metric_type == "R":
            pointer = MetricsQuery.impression
            result_pointer = func.sum(MetricsQuery.impression)
        if metric_type == "C":
            pointer = MetricsQuery.ctr
            result_pointer = func.avg(MetricsQuery.ctr)
        if not state:
            sub = select(Query).filter(Query.query.like(f"%{search_text.strip()}%")).offset(page).limit(
                per_page).subquery()
            query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                        MetricsQuery.ctr, sub.c.query).join(sub,
                                                    MetricsQuery.query_id == sub.c.id).group_by(
                sub.c.id, sub.c.query,
                MetricsQuery.date,
                MetricsQuery.position,
                MetricsQuery.clicks,
                MetricsQuery.impression,
                MetricsQuery.ctr,
            ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))

        elif state == "decrease":
            if state_type == "date":
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).filter(Query.query.like(f"%{search_text.strip()}%")).where(MetricsQuery.date == state_date).group_by(Query.query, Query.id).order_by(desc(pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
            else:
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).filter(Query.query.like(f"%{search_text.strip()}%")).where(
                    and_(MetricsQuery.date >= date_start, MetricsQuery.date <= date_end)).group_by(Query.query, Query.id).order_by(
                    desc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        
        elif state == "increase":
            if pointer == MetricsQuery.position:
                    pointer = case(
                        (pointer == 0, float('inf')),  # если pointer == 0, заменяем на float('inf')
                        else_=pointer  # иначе используем значение pointer
                    )
            if state_type == "date":
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).filter(Query.query.like(f"%{search_text.strip()}%")).where(MetricsQuery.date == state_date).group_by(Query.query, Query.id).order_by(asc(pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
            else:
                sub = select(Query).join(MetricsQuery, MetricsQuery.query_id == Query.id).filter(Query.query.like(f"%{search_text.strip()}%")).where(
                    and_(MetricsQuery.date >= date_start, MetricsQuery.date <= date_end)).group_by(Query.query, Query.id).order_by(
                    asc(result_pointer)).offset(page).limit(per_page).subquery()

                query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                            MetricsQuery.ctr, sub.c.query).join(sub,
                                                        MetricsQuery.query_id == sub.c.id).group_by(
                    sub.c.id, sub.c.query,
                    MetricsQuery.date,
                    MetricsQuery.position,
                    MetricsQuery.clicks,
                    MetricsQuery.impression,
                    MetricsQuery.ctr,
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))

        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_sort(self, page, per_page, date_start, date_end, sort_desc):
        if sort_desc:
            sub = select(Query).order_by(desc(Query.query)).offset(page).limit(
                per_page).subquery()
        else:
            sub = select(Query).order_by(Query.query).offset(page).limit(
                per_page).subquery()
        query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                       MetricsQuery.ctr, sub.c.query).join(sub,
                                                   MetricsQuery.query_id == sub.c.id).group_by(
            sub.c.id, sub.c.query,
            MetricsQuery.date,
            MetricsQuery.position,
            MetricsQuery.clicks,
            MetricsQuery.impression,
            MetricsQuery.ctr,
        ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_urls_with_pagination_and_like_sort(self, page, per_page, date_start, date_end, search_text,
                                                     sort_desc):
        if sort_desc:
            sub = select(Query).filter(Query.query.like(f"%{search_text.strip()}%")).group_by(Query.query, Query.id).order_by(desc(Query.query)).offset(
                page).limit(per_page).subquery()
        else:
            sub = select(Query).filter(Query.query.like(f"%{search_text.strip()}%")).group_by(Query.query, Query.id).order_by(Query.query).offset(
                page).limit(
                per_page).subquery()
        query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                       MetricsQuery.ctr, sub.c.query).join(sub,
                                                   MetricsQuery.query_id == sub.c.id).group_by(
            sub.c.id, sub.c.query,
            MetricsQuery.date,
            MetricsQuery.position,
            MetricsQuery.clicks,
            MetricsQuery.impression,
            MetricsQuery.ctr,
        ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_metrics_daily_summary_like(self, date_start, date_end, search_text):
        sub = select(Query).filter(Query.query.like(f"%{search_text.strip()}%")).subquery()
        query = select(MetricsQuery.date, 
                    func.sum(MetricsQuery.clicks).label('total_clicks'),
                    func.sum(MetricsQuery.impression).label('total_impressions')
                    ).join(sub, MetricsQuery.query_id == sub.c.id
                    ).group_by(MetricsQuery.date,
                    ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        
        query = select(func.count()).filter(Query.query.like(f"%{search_text.strip()}%")).limit(1)
        total_records = await self.db_session.execute(query)
        #return {"total_records": total_records, "data": product_row}
        if len(product_row) != 0:   
            return product_row, total_records.first()

    async def get_metrics_daily_summary(self, date_start, date_end):
        query = select(MetricsQuery.date, 
                    func.sum(MetricsQuery.clicks).label('total_clicks'),
                    func.sum(MetricsQuery.impression).label('total_impressions')
                    ).group_by(MetricsQuery.date,
                    ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        res = await self.db_session.execute(query)
        product_row = res.fetchall()
        
        query = select(func.count()).select_from(Query).limit(1)
        total_records = await self.db_session.execute(query)
        #for i in total_records:
        #return {"total_records": total_records, "data": product_row}
        if len(product_row) != 0:   
            return product_row, total_records.first()
        
    async def get_not_void_count_daily_summary_like(self, date_start, date_end, search_text):
        sub = select(Query).filter(Query.query.like(f"%{search_text.strip()}%")).subquery()
        sub_count_query = select(MetricsQuery.date.label("date"), func.count().label("count_line")                
                ).join(sub, MetricsQuery.query_id == sub.c.id
                ).where(MetricsQuery.position > 0
                ).group_by(MetricsQuery.date
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start)
                )
        res = await self.db_session.execute(sub_count_query)
        product_row = res.fetchall()
        
        if len(product_row) != 0:
            return product_row
        
    async def get_not_void_count_daily_summary(self, date_start, date_end):   
        sub_count_query = select(MetricsQuery.date.label("date"), func.count().label("count_line")                
                ).where(MetricsQuery.position > 0
                ).group_by(MetricsQuery.date
                ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start)
                )
        res = await self.db_session.execute(sub_count_query)
        product_row = res.fetchall()
        
        if len(product_row) != 0:
            return product_row

class MetricQueryDAL:
    """Data Access Layer for operating user info"""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_new_metrics(
            self,
            add_values
    ):
        self.db_session.add_all(add_values)
        await self.db_session.flush()
        return

    async def get_approach_query(
            self,
            session
    ):
        last_update_date = await get_last_update_date(session, MetricsQuery)
        query = select(distinct(MetricsQuery.query_id)).where(
            and_(MetricsQuery.position <= 20, MetricsQuery.date == last_update_date, MetricsQuery.position > 0))
        result = await self.db_session.execute(query)
        return result.fetchall()

    async def get_top_data(
            self,
            top: int
    ):
        query = select(MetricsQuery.impression, MetricsQuery.clicks, MetricsQuery.position, MetricsQuery.date).where(
            and_(
                MetricsQuery.position <= top, MetricsQuery.position > 0))
        result = await self.db_session.execute(query)
        return result.fetchall()

    async def delete_data(
            self,
            date
    ):
        query = delete(MetricsQuery).where(MetricsQuery.date == date)
        await self.db_session.execute(query)
        await self.db_session.commit()
    

    async def delete_days(
            self,
            days_count: int,
    ):
        target_date = datetime.now() - timedelta(days=days_count)

        query = delete(MetricsQuery).where(MetricsQuery.date >= target_date)

        await self.db_session.execute(query)

        await self.db_session.commit()

        logger.info(f"Из таблицы query были удалены данные до: {target_date}")

        return 


class IndicatorDAL:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_new_indicator(
            self,
            values
    ):

        await self.session.execute(text("TRUNCATE TABLE query_indicator RESTART IDENTITY CASCADE;"))
        await self.session.commit()

        self.session.add_all(values)
        await self.session.commit()

    async def get_indicators_from_db(
            self,
            start_date,
            end_date,
    ):
        query = select(QueryIndicator.indicator, QueryIndicator.value, QueryIndicator.date).where(
            and_(QueryIndicator.date >= start_date, QueryIndicator.date <= end_date))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def add_top(
            self,
            values
    ):
        self.session.add_all(values)
        await self.session.commit()

    async def get_top_query(
            self,
            start_date,
            end_date,
            top
    ):
        query = select(QueryUrlTop.position, QueryUrlTop.clicks, QueryUrlTop.impression, QueryUrlTop.count,
                       QueryUrlTop.date).where(and_
                                               (QueryUrlTop.type == "query",
                                                QueryUrlTop.top == top,
                                                QueryUrlTop.date >= start_date,
                                                QueryUrlTop.date <= end_date))
        result = await self.session.execute(query)
        return result.fetchall()

    async def get_top_url(
            self,
            start_date,
            end_date,
            top
    ):
        query = select(QueryUrlTop.position, QueryUrlTop.clicks, QueryUrlTop.impression, QueryUrlTop.count,
                       QueryUrlTop.date).where(and_
                                               (QueryUrlTop.type == "url",
                                                QueryUrlTop.top == top,
                                                QueryUrlTop.date >= start_date,
                                                QueryUrlTop.date <= end_date))
        result = await self.session.execute(query)
        return result.fetchall()


class MergeDAL:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_merge_with_pagination(self, date, page, per_page):
        query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).offset(page).limit(
            per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_merge_queries(self, date_start, date_end, queries: List[str]):
        sub = select(Query).where(Query.query.in_(queries)).subquery()
        query = select(MetricsQuery.date, MetricsQuery.position, MetricsQuery.clicks, MetricsQuery.impression,
                       MetricsQuery.ctr, sub).join(sub,
                                                   MetricsQuery.query == sub.c.query).group_by(
            sub.c.query,
            MetricsQuery.date,
            MetricsQuery.position,
            MetricsQuery.clicks,
            MetricsQuery.impression,
            MetricsQuery.ctr,
        ).having(and_(MetricsQuery.date <= date_end, MetricsQuery.date >= date_start))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_merge_with_pagination_sort(self, date, sort_desc, page, per_page):
        if sort_desc:
            query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(desc(QueryUrlsMerge.url)).offset(
                page).limit(
                per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        else:
            query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(QueryUrlsMerge.url).offset(
                page).limit(
                per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_merge_with_pagination_and_like(self, date, search_text_url, search_text_query, page, per_page):
        if search_text_query:
            query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).filter(
                text("EXISTS (SELECT 1 FROM unnest(queries) AS query WHERE query LIKE :search_text)")
            ).params(search_text='%' + search_text_query.strip() + '%').offset(page).limit(per_page).where(
                QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format)
            )
        elif search_text_url:
            query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).filter(
                QueryUrlsMerge.url.like(f"%{search_text_url.strip()}%")).offset(page).limit(
                per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row

    async def get_merge_with_pagination_and_like_sort(self, date, search_text_url, search_text_query, sort_desc, page,
                                                      per_page):
        if sort_desc:
            if search_text_query:
                query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(desc(QueryUrlsMerge.url)).filter(
                    text("EXISTS (SELECT 1 FROM unnest(queries) AS query WHERE query LIKE :search_text)")
                ).params(search_text='%' + search_text_query.strip() + '%').offset(page).limit(per_page).where(
                    QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format)
                )
            elif search_text_url:
                query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(desc(QueryUrlsMerge.url)).filter(
                    QueryUrlsMerge.url.like(f"%{search_text_url.strip()}%")).offset(page).limit(
                    per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        else:
            if search_text_query:
                query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(QueryUrlsMerge.url).filter(
                    text("EXISTS (SELECT 1 FROM unnest(queries) AS query WHERE query LIKE :search_text)")
                ).params(search_text='%' + search_text_query.strip() + '%').offset(page).limit(per_page).where(
                    QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format)
                )
            elif search_text_url:
                query = select(QueryUrlsMerge.url, QueryUrlsMerge.queries).order_by(QueryUrlsMerge.url).filter(
                    QueryUrlsMerge.url.like(f"%{search_text_url.strip()}%")).offset(page).limit(
                    per_page).where(QueryUrlsMerge.date == datetime.strptime(date.split()[0], date_format))
        res = await self.session.execute(query)
        product_row = res.fetchall()
        if len(product_row) != 0:
            return product_row
