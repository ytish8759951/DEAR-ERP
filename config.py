import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


GEMINI_API_KEY = os.environ.get(GEMINI_API_KEY, ")


def database_uri():
    return os.environ.get("DATABASE_URL") or "sqlite:///" + (BASE_DIR / "dear_erp.db").as_posix()


def engine_options(uri):
    if uri.startswith("postgresql"):
        return {
            "pool_pre_ping": True,
            "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
            "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", "1800")),
        }
    return {"pool_pre_ping": True}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dear-erp-dev-secret")
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = engine_options(SQLALCHEMY_DATABASE_URI)
    PRODUCT_UPLOAD_FOLDER = BASE_DIR / "static" / "uploads" / "products"
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    DEFAULT_PAGE_SIZE = 50
    PAGE_SIZE_OPTIONS = (50, 100, 200)
    LOW_STOCK_THRESHOLD = 5
    GEMINI_API_KEY = os.environ.get(GEMINI_API_KEY, ")
