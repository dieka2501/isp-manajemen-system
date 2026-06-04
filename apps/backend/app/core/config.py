from functools import lru_cache
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "ISP Manajemen Backend")
    app_env: str = os.getenv("APP_ENV", "development")
    app_debug: bool = os.getenv("APP_DEBUG", "true").lower() == "true"
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    api_v1_prefix: str = os.getenv("API_V1_PREFIX", "/api/v1")
    fonnte_api_url: str = os.getenv("FONNTE_API_URL", "https://api.fonnte.com/send")
    fonnte_token: str = os.getenv("FONNTE_TOKEN", "")
    fonnte_default_country_code: str = os.getenv("FONNTE_DEFAULT_COUNTRY_CODE", "62")
    fonnte_webhook_secret: str = os.getenv("FONNTE_WEBHOOK_SECRET", "")
    google_service_account_file: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    google_service_account_json: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    google_sheets_spreadsheet_id: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    google_sheets_worksheet_name: str = os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "incoming_whatsapp")


@lru_cache
def get_settings() -> Settings:
    return Settings()
