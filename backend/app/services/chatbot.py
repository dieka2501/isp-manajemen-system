from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore
from app.services.fonnte import FonnteClient
from app.services.isp_agent import ISPCSAgent

logger = logging.getLogger(__name__)


class ISPCSChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SQLiteChatStore(settings)
        self.fonnte = FonnteClient(settings)

    def handle_incoming_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        stored_message = self.store.save_incoming_message(payload)
        message_text = stored_message.message_text.strip()
        if not message_text:
            logger.info(
                "Incoming chat ignored conversation_id=%s device=%s sender=%s reason=empty message_text",
                stored_message.conversation_id,
                stored_message.device.device_identifier,
                stored_message.sender_number,
            )
            self.store.update_incoming_message_analysis(
                message_id=stored_message.message_id,
                matched_keywords=[],
                matched_product_names=[],
                reply_text=None,
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
                    "skipped": True,
                    "skip_reason": "empty_message_text",
                },
                "reply_attempted": False,
                "matched_products": [],
                "reply_text": None,
                "reply_sent": False,
                "send_result": None,
                "send_error": None,
                "skip_reason": "empty_message_text",
            }

        agent_response = ISPCSAgent(self.store.get_intent_agent_catalog()).answer(message_text)
        review_reason = self._learning_review_reason(agent_response)
        if review_reason:
            self.store.save_unprocessed_question(
                stored_message=stored_message,
                analysis=agent_response.as_dict(),
                reason=review_reason,
            )
        logger.info(
            "Incoming chat saved conversation_id=%s device=%s sender=%s intent=%s confidence=%s entities=%s",
            stored_message.conversation_id,
            stored_message.device.device_identifier,
            stored_message.sender_number,
            agent_response.intent.intent_code,
            agent_response.intent.confidence,
            ",".join(entity.entity_code for entity in agent_response.entities) or "-",
        )

        reply_text = agent_response.reply_text
        send_result: dict[str, Any] | None = None
        send_error: str | None = None

        try:
            send_result = self.fonnte.send_message(
                target_number=stored_message.sender_number,
                message=reply_text,
                auth_token=stored_message.device.outbound_token,
            )
            logger.info(
                "CS/Sales reply sent conversation_id=%s sender=%s",
                stored_message.conversation_id,
                stored_message.sender_number,
            )
            self.store.save_outgoing_message(
                conversation_id=stored_message.conversation_id,
                reply_text=reply_text,
                matched_keywords=agent_response.intent.matched_keywords,
                matched_product_names=[],
                raw_payload=send_result,
            )
        except Exception as exc:
            send_error = str(exc)
            logger.warning(
                "CS/Sales reply send failed conversation_id=%s error=%s",
                stored_message.conversation_id,
                exc,
            )

        self.store.update_incoming_message_analysis(
            message_id=stored_message.message_id,
            matched_keywords=agent_response.intent.matched_keywords,
            matched_product_names=[],
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
            "analysis": agent_response.as_dict(),
            "reply_attempted": reply_text is not None,
            "matched_products": [],
            "reply_text": reply_text,
            "reply_sent": send_result is not None,
            "send_result": send_result,
            "send_error": send_error,
            "skip_reason": None,
        }

    def _learning_review_reason(self, agent_response: Any) -> str | None:
        if agent_response.intent.intent_code == "unknown":
            return "unknown_intent"
        if agent_response.intent.confidence < 0.35:
            return "low_confidence"
        return None
