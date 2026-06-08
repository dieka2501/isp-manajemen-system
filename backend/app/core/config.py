from functools import lru_cache
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "ISP Manajemen Backend")
    app_env: str = os.getenv("APP_ENV", "development")
    app_debug: bool = os.getenv("APP_DEBUG", "true").lower() == "true"
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
    api_v1_prefix: str = os.getenv("API_V1_PREFIX", "/api/v1")
    fonnte_api_url: str = os.getenv("FONNTE_API_URL", "https://api.fonnte.com/send")
    fonnte_token: str = os.getenv("FONNTE_TOKEN", "")
    fonnte_default_country_code: str = os.getenv("FONNTE_DEFAULT_COUNTRY_CODE", "62")
    fonnte_webhook_secret: str = os.getenv("FONNTE_WEBHOOK_SECRET", "")
    chat_database_path: str = os.getenv(
        "CHAT_DATABASE_PATH",
        str(BASE_DIR / "data" / "chat.sqlite3"),
    )
    chat_auto_account_name: str = os.getenv("CHAT_AUTO_ACCOUNT_NAME", "Auto Ingest Account")
    chat_auto_account_slug: str = os.getenv("CHAT_AUTO_ACCOUNT_SLUG", "auto-ingest")
    sqlite_explorer_sources_json: str = os.getenv("SQLITE_EXPLORER_SOURCES_JSON", "")
    dashboard_secret: str = os.getenv("DASHBOARD_SECRET", "")
    dashboard_cookie_name: str = os.getenv(
        "DASHBOARD_COOKIE_NAME",
        "sqlite_dashboard_session",
    )
    dashboard_session_hours: int = int(os.getenv("DASHBOARD_SESSION_HOURS", "12"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
