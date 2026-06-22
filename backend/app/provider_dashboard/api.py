from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.chat import chat_router
from app.api.sqlite_explorer import sqlite_explorer_router
from app.core.config import get_settings
from app.provider_dashboard.message_dumps import provider_message_dump_router
from app.services.dashboard_auth import DashboardAuthService

provider_api_router = APIRouter(prefix="/provider")


class ProviderLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1)


@provider_api_router.get("/auth/status", tags=["provider-auth"])
def auth_status(request: Request) -> dict[str, object]:
    return DashboardAuthService(get_settings()).status(request).as_dict()


@provider_api_router.post("/auth/login", tags=["provider-auth"])
def auth_login(payload: ProviderLoginRequest, response: Response) -> dict[str, object]:
    settings = get_settings()
    state = DashboardAuthService(settings).login(payload.password, response)
    response.delete_cookie(key=settings.client_dashboard_cookie_name, path="/")
    return state.as_dict()


@provider_api_router.post("/auth/logout", tags=["provider-auth"])
def auth_logout(response: Response) -> dict[str, str]:
    DashboardAuthService(get_settings()).logout(response)
    return {"status": "ok"}


provider_api_router.include_router(chat_router, prefix="/chat")
provider_api_router.include_router(provider_message_dump_router, prefix="/message-dumps")
provider_api_router.include_router(sqlite_explorer_router, prefix="/sqlite")
