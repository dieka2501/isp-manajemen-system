from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import Settings
from app.services.isp_agent import AgentResponse, normalize_text

logger = logging.getLogger(__name__)


DEFAULT_RESPONSE_RULES = {
    "language": "id",
    "tone": "friendly, helpful, semi-informal ISP customer service",
    "channel": "whatsapp",
    "max_sentences": 4,
    "avoid_repeating_previous_answer": True,
    "do_not_invent_data": True,
    "ask_clarification_if_missing_required_info": True,
    "use_kak": True,
}


class LLMResponseGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_reply(
        self,
        *,
        user_message: str,
        agent_response: AgentResponse,
        conversation_state: dict[str, Any] | None,
        knowledge: dict[str, Any],
        native_reply: str,
    ) -> str:
        if not self.settings.llm_response_enabled or not self.settings.openai_api_key:
            return native_reply

        prompt = self.build_prompt(
            user_message=user_message,
            agent_response=agent_response,
            conversation_state=conversation_state,
            knowledge=knowledge,
            native_reply=native_reply,
        )
        try:
            generated = self._call_openai(prompt).strip()
        except ValueError as exc:
            logger.warning("LLM response generation skipped: %s", exc)
            return native_reply

        if not generated:
            return native_reply

        last_response = str((conversation_state or {}).get("last_bot_response") or "")
        if last_response and self.is_too_similar(generated, last_response):
            concise = self._concise_followup_reply(agent_response, knowledge)
            if concise:
                return concise
        return generated

    def build_prompt(
        self,
        *,
        user_message: str,
        agent_response: AgentResponse,
        conversation_state: dict[str, Any] | None,
        knowledge: dict[str, Any],
        native_reply: str,
    ) -> str:
        payload = {
            "customer_message": user_message,
            "conversation_state": self._safe_state(conversation_state),
            "detected_intent": agent_response.intent.as_dict(),
            "entities": [entity.as_dict() for entity in agent_response.entities],
            "knowledge": knowledge,
            "native_fallback_reply": native_reply,
            "response_rules": DEFAULT_RESPONSE_RULES,
        }
        return (
            "You are a customer service assistant for an Indonesian ISP.\n"
            "Generate the final WhatsApp reply using ONLY the facts in the Knowledge section.\n"
            "Do not invent package prices, coverage, payment availability, promos, or schedules.\n"
            "If data is missing or unknown, ask one short clarification question.\n"
            "Do not repeat the previous bot response; answer the specific follow-up.\n"
            "Keep the reply natural, friendly, and concise.\n\n"
            f"Context JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def is_too_similar(self, new_response: str, last_response: str) -> bool:
        new_tokens = set(normalize_text(new_response).split())
        last_tokens = set(normalize_text(last_response).split())
        if not new_tokens or not last_tokens:
            return False
        return len(new_tokens & last_tokens) / len(new_tokens | last_tokens) > 0.85

    def _call_openai(self, prompt: str) -> str:
        request = urllib.request.Request(
            self.settings.openai_responses_url,
            data=json.dumps(
                {
                    "model": self.settings.openai_model,
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": prompt}],
                        }
                    ],
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.openai_timeout_seconds,
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("OpenAI response HTTP error status=%s body=%s", exc.code, body)
            raise ValueError(f"OpenAI request failed with status {exc.code}.") from exc
        except urllib.error.URLError as exc:
            raise ValueError("OpenAI request failed due to a network error.") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("OpenAI returned invalid JSON.") from exc

        output_text = data.get("output_text")
        if isinstance(output_text, str):
            return output_text
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text")
                if isinstance(text, str):
                    return text
        return ""

    def _safe_state(self, conversation_state: dict[str, Any] | None) -> dict[str, Any]:
        state = conversation_state or {}
        return {
            "current_topic": state.get("current_topic"),
            "current_intent": state.get("current_intent"),
            "waiting_for": state.get("waiting_for") or [],
            "collected_slots": state.get("collected_slots") or {},
            "last_user_message": state.get("last_user_message"),
            "last_bot_response": state.get("last_bot_response") or state.get("last_bot_question"),
        }

    def _concise_followup_reply(
        self,
        agent_response: AgentResponse,
        knowledge: dict[str, Any],
    ) -> str | None:
        if agent_response.intent.intent_code == "ask_payment_method":
            methods = knowledge.get("data", {}).get("payment_methods") or []
            if len(methods) == 1 and int(methods[0].get("is_available", 0) or 0) == 1:
                return f"Bisa Kak, pembayaran lewat {methods[0]['method_name']} tersedia."
        return None
