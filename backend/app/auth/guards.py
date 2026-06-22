from __future__ import annotations

from collections.abc import Callable

from fastapi import Header, HTTPException, Request, status

from app.auth.roles import ActorRole
from app.client_dashboard.permissions import ClientPermission
from app.core.config import get_settings
from app.provider_dashboard.permissions import ProviderPermission
from app.services.client_dashboard_auth import ClientAuthSession, ClientDashboardTokenService
from app.services.dashboard_auth import DashboardAuthService, DashboardAuthState


def _client_session_from_request(
    request: Request,
    authorization: str | None = None,
) -> ClientAuthSession | None:
    settings = get_settings()
    token_service = ClientDashboardTokenService(settings)
    cookie_token = request.cookies.get(settings.client_dashboard_cookie_name)
    if cookie_token:
        session = token_service.session_from_token(cookie_token)
        if session:
            return session
    if authorization and authorization.startswith("Bearer "):
        return token_service.session_from_token(authorization.removeprefix("Bearer ").strip())
    return None


def require_provider(
    request: Request,
    permission: ProviderPermission,
) -> DashboardAuthState:
    settings = get_settings()
    provider_auth = DashboardAuthService(settings)
    state = provider_auth.status(request)
    if state.authenticated:
        return provider_auth.require_permission(request, permission.value)
    client_cookie = request.cookies.get(settings.client_dashboard_cookie_name)
    client_actor = ClientDashboardTokenService(settings).actor_from_token(client_cookie)
    if client_actor or _client_session_from_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client users cannot access Provider operations.",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Provider dashboard login required.",
    )


def provider_guard(
    permission: ProviderPermission,
) -> Callable[[Request], DashboardAuthState]:
    def dependency(request: Request) -> DashboardAuthState:
        return require_provider(request, permission)

    return dependency


def require_client(
    request: Request,
    authorization: str | None = None,
    permission: ClientPermission = ClientPermission.DASHBOARD_ACCESS,
) -> ClientAuthSession:
    settings = get_settings()
    cookie_token = request.cookies.get(settings.client_dashboard_cookie_name)
    try:
        return ClientDashboardTokenService(settings).require_session(
            authorization=authorization,
            cookie_token=cookie_token,
            permission=permission.value,
        )
    except HTTPException as exc:
        provider_state = DashboardAuthService(settings).status(request)
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and provider_state.authenticated:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provider users cannot access Client operations.",
            ) from exc
        raise


def client_dashboard_guard(
    request: Request,
    authorization: str | None = Header(default=None),
) -> ClientAuthSession:
    return require_client(request, authorization)


def dashboard_destination(request: Request) -> str:
    settings = get_settings()
    provider_state = DashboardAuthService(settings).status(request)
    client_auth = ClientDashboardTokenService(settings)
    client_cookie = request.cookies.get(settings.client_dashboard_cookie_name)
    client_actor = client_auth.actor_from_token(client_cookie)
    client_session = client_auth.session_from_token(client_cookie)

    if provider_state.authenticated and provider_state.actor != ActorRole.PROVIDER.value:
        return "/unauthorized"
    if client_actor and client_actor != ActorRole.CLIENT.value:
        return "/unauthorized"
    if provider_state.authenticated and client_session:
        return "/unauthorized"
    if provider_state.authenticated:
        return "/sqlexplore"
    if client_session:
        return "/client-dashboard"
    return "/login"
