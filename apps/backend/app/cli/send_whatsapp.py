import argparse
import json
import re
import sys
from urllib import error, parse, request

from app.core.config import get_settings


def normalize_number(number: str, country_code: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", number.strip())
    if cleaned.startswith("+"):
        return cleaned[1:]

    digits_only = re.sub(r"\D", "", cleaned)
    if digits_only.startswith("0"):
        return f"{country_code}{digits_only[1:]}"

    return digits_only


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a WhatsApp message through the Fonnte API."
    )
    parser.add_argument(
        "-n",
        "--number",
        required=True,
        help="Target WhatsApp number. Example: 08123456789",
    )
    parser.add_argument(
        "-m",
        "--message",
        required=True,
        help="Message body to send.",
    )
    parser.add_argument(
        "--country-code",
        default=None,
        help="Override default country code for local numbers. Example: 62",
    )
    return parser.parse_args()


def send_message(number: str, message: str, country_code: str) -> int:
    settings = get_settings()
    if not settings.fonnte_token:
        print("FONNTE_TOKEN is not set. Please update your environment first.", file=sys.stderr)
        return 1

    payload = parse.urlencode(
        {
            "target": normalize_number(number, country_code),
            "message": message,
            "countryCode": country_code,
        }
    ).encode("utf-8")

    req = request.Request(
        settings.fonnte_api_url,
        data=payload,
        headers={
            "Authorization": settings.fonnte_token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
            try:
                print(json.dumps(json.loads(raw_body), indent=2))
            except json.JSONDecodeError:
                print(raw_body)
            return 0
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Request failed: {exc.reason}", file=sys.stderr)
        return 1


def main() -> int:
    args = parse_args()
    settings = get_settings()
    country_code = args.country_code or settings.fonnte_default_country_code
    return send_message(args.number, args.message, country_code)


if __name__ == "__main__":
    raise SystemExit(main())
