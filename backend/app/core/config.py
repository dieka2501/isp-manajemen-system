from functools import lru_cache
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return ""


def _version_from_file() -> str:
    version_file = PROJECT_ROOT / "VERSION"
    if not version_file.exists():
        return "dev"
    value = version_file.read_text(encoding="utf-8").strip()
    return value or "dev"


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
    app_version: str = os.getenv("APP_VERSION", _version_from_file())
    app_build_commit: str = _first_env(
        "APP_BUILD_COMMIT",
        "RAILWAY_GIT_COMMIT_SHA",
        "RENDER_GIT_COMMIT",
        "VERCEL_GIT_COMMIT_SHA",
        "GIT_COMMIT_SHA",
        "COMMIT_SHA",
        "SOURCE_VERSION",
    )
    app_build_branch: str = _first_env(
        "APP_BUILD_BRANCH",
        "RAILWAY_GIT_BRANCH",
        "VERCEL_GIT_COMMIT_REF",
        "GIT_BRANCH",
    )
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
    client_dashboard_token_hours: int = int(os.getenv("CLIENT_DASHBOARD_TOKEN_HOURS", "2"))
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
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", os.getenv("APP_PUBLIC_BASE_URL", ""))
    registration_offer_message_threshold: int = int(
        os.getenv("REGISTRATION_OFFER_MESSAGE_THRESHOLD", "5")
    )
    registration_default_payment_amount: int = int(
        os.getenv("REGISTRATION_DEFAULT_PAYMENT_AMOUNT", "0")
    )
    virtual_account_prefix: str = os.getenv("VIRTUAL_ACCOUNT_PREFIX", "ISP")
    technician_whatsapp_numbers: str = os.getenv("TECHNICIAN_WHATSAPP_NUMBERS", "")
    payment_webhook_secret: str = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    payment_proof_upload_dir: str = _project_path_from_env(
        "PAYMENT_PROOF_UPLOAD_DIR",
        BASE_DIR / "data" / "payment_proofs",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
