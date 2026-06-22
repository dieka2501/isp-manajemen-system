from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, Response, status

from app.core.config import Settings
from app.auth.roles import ActorRole
from app.provider_dashboard.permissions import ALL_PROVIDER_PERMISSIONS


@dataclass(frozen=True)
class DashboardAuthState:
    authenticated: bool
    secret_configured: bool
    expires_at: int | None = None
    actor: str | None = None
    permissions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "authenticated": self.authenticated,
            "secret_configured": self.secret_configured,
            "expires_at": self.expires_at,
            "actor": self.actor,
            "permissions": list(self.permissions),
        }


class DashboardAuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def status(self, request: Request) -> DashboardAuthState:
        if not self.settings.dashboard_secret:
            return DashboardAuthState(authenticated=False, secret_configured=False)

        token = request.cookies.get(self.settings.dashboard_cookie_name)
        payload = self._decode_token(token) if token else None
        if not payload:
            return DashboardAuthState(authenticated=False, secret_configured=True)

        return DashboardAuthState(
            authenticated=True,
            secret_configured=True,
            expires_at=int(payload["exp"]),
            actor=str(payload.get("actor") or ActorRole.PROVIDER.value),
            permissions=tuple(
                str(permission)
                for permission in payload.get("permissions", sorted(ALL_PROVIDER_PERMISSIONS))
            ),
        )

    def login(self, password: str, response: Response) -> DashboardAuthState:
        if not self.settings.dashboard_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provider dashboard authentication is not configured.",
            )

        if not hmac.compare_digest(password, self.settings.dashboard_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid dashboard password.",
            )

        expires_at = int(time.time()) + (self.settings.dashboard_session_hours * 3600)
        token = self._encode_token(expires_at)
        response.set_cookie(
            key=self.settings.dashboard_cookie_name,
            value=token,
            httponly=True,
            samesite="lax",
            secure=self.settings.dashboard_cookie_secure,
            path="/",
            max_age=self.settings.dashboard_session_hours * 3600,
        )
        return DashboardAuthState(
            authenticated=True,
            secret_configured=True,
            expires_at=expires_at,
            actor=ActorRole.PROVIDER.value,
            permissions=tuple(sorted(ALL_PROVIDER_PERMISSIONS)),
        )

    def logout(self, response: Response) -> None:
        response.delete_cookie(
            key=self.settings.dashboard_cookie_name,
            path="/",
        )

    def require_auth(self, request: Request) -> None:
        state = self.status(request)
        if state.authenticated and state.actor == ActorRole.PROVIDER.value:
            return
        if state.authenticated:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provider role is required.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dashboard login required.",
        )

    def require_permission(self, request: Request, permission: str) -> DashboardAuthState:
        state = self.status(request)
        if not state.authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Provider dashboard login required.",
            )
        if state.actor != ActorRole.PROVIDER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Provider role is required.",
            )
        if permission not in state.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Provider permission `{permission}` is required.",
            )
        return state

    def _encode_token(self, expires_at: int) -> str:
        payload = json.dumps(
            {
                "actor": ActorRole.PROVIDER.value,
                "exp": expires_at,
                "permissions": sorted(ALL_PROVIDER_PERMISSIONS),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        signature = hmac.new(
            self.settings.dashboard_secret.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{encoded_payload}.{signature}"

    def _decode_token(self, token: str | None) -> dict[str, Any] | None:
        if not token or "." not in token:
            return None

        encoded_payload, signature = token.split(".", 1)
        expected_signature = hmac.new(
            self.settings.dashboard_secret.encode("utf-8"),
            encoded_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        padded = encoded_payload + "=" * (-len(encoded_payload) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

        try:
            exp = int(payload.get("exp", 0))
        except (TypeError, ValueError):
            return None
        if exp < int(time.time()):
            return None
        actor = str(payload.get("actor") or ActorRole.PROVIDER.value)
        permissions = payload.get("permissions")
        if not isinstance(permissions, list):
            permissions = sorted(ALL_PROVIDER_PERMISSIONS)
        return {
            "actor": actor,
            "exp": exp,
            "permissions": [str(permission) for permission in permissions],
        }
