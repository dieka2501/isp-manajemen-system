from functools import lru_cache
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _project_path_from_env(name: str, default: Path) -> str:
    value = os.getenv(name)
    if not value:
        return str(default)
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_responses_url: str = os.getenv(
        "OPENAI_RESPONSES_URL",
        "https://api.openai.com/v1/responses",
    )
    openai_timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
    llm_response_enabled: bool = os.getenv("LLM_RESPONSE_ENABLED", "true").lower() == "true"
    conversation_state_ttl_hours: int = int(os.getenv("CONVERSATION_STATE_TTL_HOURS", "48"))
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
    client_dashboard_jwt_secret: str = (
        os.getenv("CLIENT_DASHBOARD_JWT_SECRET")
        or os.getenv("DASHBOARD_SECRET")
        or "dev-client-dashboard-secret"
    )
    client_dashboard_token_hours: int = int(os.getenv("CLIENT_DASHBOARD_TOKEN_HOURS", "12"))
    client_dashboard_seed_email: str = os.getenv(
        "CLIENT_DASHBOARD_SEED_EMAIL",
        "admin@isp.local",
    )
    client_dashboard_seed_password: str = os.getenv(
        "CLIENT_DASHBOARD_SEED_PASSWORD",
        "password",
    )
    client_dashboard_seed_office_address: str = os.getenv(
        "CLIENT_DASHBOARD_SEED_OFFICE_ADDRESS",
        "Kantor ISP",
    )
    client_dashboard_seed_pic_name: str = os.getenv(
        "CLIENT_DASHBOARD_SEED_PIC_NAME",
        "Admin ISP",
    )
    billing_sample_xlsx_path: str = _project_path_from_env(
        "BILLING_SAMPLE_XLSX_PATH",
        PROJECT_ROOT / "contoh-list-billing.xlsx",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
