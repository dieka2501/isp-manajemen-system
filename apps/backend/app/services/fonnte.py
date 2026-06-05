from __future__ import annotations

import json
import re
from urllib import error, parse, request

from app.core.config import Settings


def normalize_number(number: str, country_code: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", number.strip())
    if cleaned.startswith("+"):
        return cleaned[1:]

    digits_only = re.sub(r"\D", "", cleaned)
    if digits_only.startswith("0"):
        return f"{country_code}{digits_only[1:]}"

    return digits_only


class FonnteClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_message(
        self,
        *,
        target_number: str,
        message: str,
        auth_token: str | None = None,
        country_code: str | None = None,
    ) -> dict:
        token = auth_token or self.settings.fonnte_token
        if not token:
            raise ValueError("FONNTE token is not configured for this device/client.")

        resolved_country_code = country_code or self.settings.fonnte_default_country_code
        payload = parse.urlencode(
            {
                "target": normalize_number(target_number, resolved_country_code),
                "message": message,
                "countryCode": resolved_country_code,
            }
        ).encode("utf-8")

        req = request.Request(
            self.settings.fonnte_api_url,
            data=payload,
            headers={
                "Authorization": token,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {"raw_response": body}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Fonnte HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Fonnte request failed: {exc.reason}") from exc
