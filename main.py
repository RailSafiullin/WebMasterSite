from contextlib import asynccontextmanager

from apscheduler.triggers.cron import CronTrigger
import uvicorn
from starlette.middleware.sessions import SessionMiddleware

# import settings
import config
from fastapi import FastAPI, HTTPException
from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from api.admin_handlers import admin_router
from api.auth.auth_config import fastapi_users, auth_backend
from api.auth.http_exception import http_exception_handler
from api.auth.schemas import UserRead, UserCreate

from api.services.router import router as services_router

from api.config.router import router as config_router
from api.config.models import AutoUpdatesMode
from api.config.utils import load_auto_updates_schedule, update_list
from api.auth.router import router as auth_router
from db.session import async_session_general
from config import SECRET
from scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    yield


app = FastAPI(
    title="Metrics urls",
    redoc_url=None,
    docs_url="/docs",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS

origins = [
    "http://192.168.1.79:8001",
]

app.add_exception_handler(HTTPException, http_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionMiddleware, secret_key=SECRET)

main_api_router = APIRouter()
main_api_router.include_router(admin_router, prefix="/admin")

app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(main_api_router)

app.include_router(auth_router)

app.include_router(services_router, prefix="/services")

app.include_router(config_router, prefix="/config")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
