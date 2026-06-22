from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from app.core.config import Settings
from app.auth.roles import ActorRole
from app.client_dashboard.permissions import ALL_CLIENT_PERMISSIONS


@dataclass(frozen=True)
class ClientAuthSession:
    client_id: int
    actor: str
    expires_at: int
    permissions: tuple[str, ...]


class ClientDashboardTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def issue_token(self, client_id: int) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + (self.settings.client_dashboard_token_hours * 3600)
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "actor": ActorRole.CLIENT.value,
            "sub": str(client_id),
            "iat": now,
            "exp": expires_at,
            "permissions": sorted(ALL_CLIENT_PERMISSIONS),
        }
        signing_input = ".".join(
            [
                self._encode_json(header),
                self._encode_json(payload),
            ]
        )
        signature = self._sign(signing_input)
        return f"{signing_input}.{signature}", expires_at

    def require_session(
        self,
        authorization: str | None = None,
        cookie_token: str | None = None,
        permission: str | None = None,
    ) -> ClientAuthSession:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization.removeprefix("Bearer ").strip()
        if not token:
            token = cookie_token
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client dashboard session is required.",
            )
        actor = self.actor_from_token(token)
        if actor and actor != ActorRole.CLIENT.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client role is required.",
            )
        session = self.session_from_token(token)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            )
        if permission and permission not in session.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Client permission `{permission}` is required.",
            )
        return session

    def require_client_id(
        self,
        authorization: str | None = None,
        cookie_token: str | None = None,
    ) -> int:
        return self.require_session(authorization, cookie_token).client_id

    def session_from_token(self, token: str | None) -> ClientAuthSession | None:
        if not token:
            return None
        payload = self._decode_token(token)
        if not payload:
            return None
        actor = str(payload.get("actor") or ActorRole.CLIENT.value)
        if actor != ActorRole.CLIENT.value:
            return None
        try:
            client_id = int(payload["sub"])
            expires_at = int(payload["exp"])
        except (KeyError, TypeError, ValueError):
            return None
        permissions = payload.get("permissions")
        if not isinstance(permissions, list):
            permissions = sorted(ALL_CLIENT_PERMISSIONS)
        return ClientAuthSession(
            client_id=client_id,
            actor=actor,
            expires_at=expires_at,
            permissions=tuple(str(permission) for permission in permissions),
        )

    def actor_from_token(self, token: str | None) -> str | None:
        if not token:
            return None
        payload = self._decode_token(token)
        if not payload:
            return None
        return str(payload.get("actor") or ActorRole.CLIENT.value)

    def _decode_token(self, token: str) -> dict[str, Any] | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = ".".join(parts[:2])
        expected_signature = self._sign(signing_input)
        if not hmac.compare_digest(parts[2], expected_signature):
            return None
        try:
            payload = json.loads(self._decode_base64(parts[1]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        try:
            expires_at = int(payload.get("exp", 0))
        except (TypeError, ValueError):
            return None
        now = int(time.time())
        if expires_at <= now:
            return None
        try:
            issued_at = int(payload.get("iat", 0))
        except (TypeError, ValueError):
            return None
        max_session_age = self.settings.client_dashboard_token_hours * 3600
        if max_session_age > 0 and issued_at + max_session_age <= now:
            return None
        return payload

    def _encode_json(self, value: dict[str, Any]) -> str:
        return self._encode_base64(
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )

    def _encode_base64(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    def _decode_base64(self, value: str) -> bytes:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def _sign(self, signing_input: str) -> str:
        digest = hmac.new(
            self.settings.client_dashboard_jwt_secret.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return self._encode_base64(digest)
