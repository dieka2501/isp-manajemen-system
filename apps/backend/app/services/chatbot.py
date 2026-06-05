from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore
from app.services.fonnte import FonnteClient
from app.services.google_sheets import GoogleSheetsLogger, StockMatch

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


@dataclass(frozen=True)
class ChatAnalysis:
    should_lookup_stock: bool
    trigger_keywords: list[str]
    search_tokens: list[str]


class InventoryChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteChatStore(settings)
        self.sheets = GoogleSheetsLogger(settings)
        self.fonnte = FonnteClient(settings)

    def handle_incoming_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        stored_message = self.store.save_incoming_message(payload)
        analysis = self._analyze_message(payload)
        logger.info(
            "Incoming chat saved conversation_id=%s device=%s sender=%s triggers=%s tokens=%s",
            stored_message.conversation_id,
            stored_message.device.device_identifier,
            stored_message.sender_number,
            ",".join(analysis.trigger_keywords) or "-",
            ",".join(analysis.search_tokens) or "-",
        )

        sheet_log_result: dict[str, Any] | None = None
        sheet_log_error: str | None = None
        if self.settings.google_sheets_spreadsheet_id:
            try:
                sheet_log_result = self.sheets.append_whatsapp_message(payload)
                logger.info(
                    "Inbound payload appended to Google Sheets conversation_id=%s",
                    stored_message.conversation_id,
                )
            except Exception as exc:
                sheet_log_error = str(exc)
                logger.warning("Failed to append inbound payload to Google Sheets: %s", exc)

        matched_products: list[StockMatch] = []
        reply_text: str | None = None
        send_result: dict[str, Any] | None = None
        send_error: str | None = None

        if analysis.should_lookup_stock and analysis.search_tokens:
            logger.info(
                "Looking up stock for conversation_id=%s tokens=%s",
                stored_message.conversation_id,
                ",".join(analysis.search_tokens),
            )
            try:
                matched_products = self.sheets.search_stock_products(analysis.search_tokens)
            except Exception as exc:
                send_error = f"Stock lookup failed: {exc}"
                logger.warning(
                    "Stock lookup failed conversation_id=%s error=%s",
                    stored_message.conversation_id,
                    exc,
                )

            if matched_products:
                reply_text = self._compose_reply(matched_products)
                logger.info(
                    "Stock matched conversation_id=%s products=%s reply=%s",
                    stored_message.conversation_id,
                    ",".join(item.product_name for item in matched_products),
                    reply_text,
                )
                try:
                    send_result = self.fonnte.send_message(
                        target_number=stored_message.sender_number,
                        message=reply_text,
                        auth_token=stored_message.device.outbound_token,
                    )
                    logger.info(
                        "Reply sent conversation_id=%s sender=%s",
                        stored_message.conversation_id,
                        stored_message.sender_number,
                    )
                    self.store.save_outgoing_message(
                        conversation_id=stored_message.conversation_id,
                        reply_text=reply_text,
                        matched_keywords=analysis.trigger_keywords,
                        matched_product_names=[item.product_name for item in matched_products],
                        raw_payload=send_result,
                    )
                except Exception as exc:
                    send_error = str(exc)
                    logger.warning(
                        "Reply send failed conversation_id=%s error=%s",
                        stored_message.conversation_id,
                        exc,
                    )
            else:
                logger.info(
                    "No stock match found conversation_id=%s tokens=%s",
                    stored_message.conversation_id,
                    ",".join(analysis.search_tokens),
                )
        else:
            logger.info(
                "Reply skipped conversation_id=%s reason=%s",
                stored_message.conversation_id,
                "no trigger keywords" if not analysis.should_lookup_stock else "no search tokens",
            )

        self.store.update_incoming_message_analysis(
            message_id=stored_message.message_id,
            matched_keywords=analysis.trigger_keywords,
            matched_product_names=[item.product_name for item in matched_products],
            reply_text=reply_text,
        )

        return {
            "conversation_id": stored_message.conversation_id,
            "message_id": stored_message.message_id,
            "client": {
                "id": stored_message.device.client_id,
                "name": stored_message.device.client_name,
                "token": stored_message.device.client_token,
                "account_slug": stored_message.device.account_slug,
            },
            "device": {
                "id": stored_message.device.device_id,
                "identifier": stored_message.device.device_identifier,
                "name": stored_message.device.device_name,
            },
            "analysis": {
                "should_lookup_stock": analysis.should_lookup_stock,
                "trigger_keywords": analysis.trigger_keywords,
                "search_tokens": analysis.search_tokens,
            },
            "reply_attempted": reply_text is not None,
            "matched_products": [item.as_dict() for item in matched_products],
            "reply_text": reply_text,
            "reply_sent": send_result is not None,
            "send_result": send_result,
            "send_error": send_error,
            "sheets_log_error": sheet_log_error,
            "sheets_log_updates": sheet_log_result.get("updates") if sheet_log_result else None,
        }

    def _analyze_message(self, payload: dict[str, Any]) -> ChatAnalysis:
        message_text = str(payload.get("message") or payload.get("text") or payload.get("body") or "")
        normalized = _normalize_text(message_text)
        words = normalized.split()
        trigger_keywords = [
            keyword
            for keyword in self.settings.chat_trigger_keywords
            if keyword in words or keyword in normalized
        ]
        search_tokens = [
            token
            for token in words
            if token not in self.settings.chat_trigger_keywords and len(token) > 1
        ]
        deduplicated_tokens = list(dict.fromkeys(search_tokens))
        logger.info(
            "Analyzed message normalized=%s triggers=%s tokens=%s",
            normalized,
            ",".join(trigger_keywords) or "-",
            ",".join(deduplicated_tokens) or "-",
        )

        return ChatAnalysis(
            should_lookup_stock=bool(trigger_keywords),
            trigger_keywords=trigger_keywords,
            search_tokens=deduplicated_tokens,
        )

    def _compose_reply(self, matches: list[StockMatch]) -> str:
        lines: list[str] = []
        for match in matches[:5]:
            suffix = f" {match.product_type}" if match.product_type else ""
            lines.append(
                f"Untuk {match.product_name}{suffix} mempunyai stock {match.stock} buah."
            )
        return "\n".join(lines)
