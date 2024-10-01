from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

APP_PORT = int(os.environ.get("APP_PORT"))
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST =os.environ.get( "DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
SECRET = os.environ.get("SECRET")


MONTHLY_REQUEST_LIMIT = os.environ.get("MONTHLY_REQUEST_LIMIT")

DATABASE_GENERAL_NAME = os.environ.get("DATABASE_GENERAL_NAME")

@dataclass
class XMLConfig:
    API_URL: str
    USER_ID: str
    API_KEY: str
    GROUP_BY: str
    DOMAIN: str
    LR: str
    DEVICE: str

xml_config = XMLConfig(
    API_URL=    os.environ.get("API_URL"),
    USER_ID=    os.environ.get("USER_ID"),
    API_KEY=    os.environ.get("API_KEY"),
    GROUP_BY=   os.environ.get("GROUP_BY"),
    DOMAIN=     os.environ.get("DOMAIN"),
    LR=         os.environ.get("LR"),
    DEVICE=     os.environ.get("DEVICE"),
)