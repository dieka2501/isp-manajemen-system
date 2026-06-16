from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, status

from app.core.config import Settings


class ClientDashboardTokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def issue_token(self, client_id: int) -> tuple[str, int]:
        now = int(time.time())
        expires_at = now + (self.settings.client_dashboard_token_hours * 3600)
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": str(client_id),
            "iat": now,
            "exp": expires_at,
        }
        signing_input = ".".join(
            [
                self._encode_json(header),
                self._encode_json(payload),
            ]
        )
        signature = self._sign(signing_input)
        return f"{signing_input}.{signature}", expires_at

    def require_client_id(self, authorization: str | None) -> int:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token is required.",
            )
        token = authorization.removeprefix("Bearer ").strip()
        payload = self._decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
            )
        try:
            return int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject.",
            ) from exc

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
        if expires_at < int(time.time()):
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
