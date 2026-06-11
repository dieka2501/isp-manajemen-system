from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OpenAILearningHelper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def suggest_mapping(
        self,
        *,
        question: dict[str, Any],
        intents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")

        payload = {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._system_prompt(),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {
                                    "question": self._safe_question(question),
                                    "available_intents": self._safe_intents(intents),
                                },
                                ensure_ascii=True,
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "learning_mapping_suggestion",
                    "strict": True,
                    "schema": self._schema(),
                }
            },
        }
        response = self._post_json(payload)
        suggestion = self._extract_json_response(response)
        return self._normalize_suggestion(suggestion, intents)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.settings.openai_responses_url,
            data=json.dumps(payload).encode("utf-8"),
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
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.warning("OpenAI learning helper HTTP error status=%s body=%s", exc.code, body)
            raise ValueError(f"OpenAI request failed with status {exc.code}.") from exc
        except urllib.error.URLError as exc:
            logger.warning("OpenAI learning helper network error: %s", exc)
            raise ValueError("OpenAI request failed due to a network error.") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("OpenAI returned an invalid JSON response.") from exc

    def _extract_json_response(self, response: dict[str, Any]) -> dict[str, Any]:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return json.loads(output_text)

        for item in response.get("output") or []:
            for content in item.get("content") or []:
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return json.loads(text)
        raise ValueError("OpenAI response did not contain suggestion JSON.")

    def _normalize_suggestion(
        self,
        suggestion: dict[str, Any],
        intents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        intent_codes = {str(item["intent_code"]) for item in intents}
        intent_code = str(suggestion.get("intent_code") or "")
        mapping_type = str(suggestion.get("mapping_type") or "sample").lower()
        if intent_code not in intent_codes:
            mapping_type = "ignore"
            intent_code = ""
        if mapping_type not in {"sample", "keyword", "both", "ignore"}:
            mapping_type = "sample"

        try:
            weight = int(suggestion.get("weight") or 4)
        except (TypeError, ValueError):
            weight = 4

        return {
            "intent_code": intent_code or None,
            "mapping_type": mapping_type,
            "keyword": self._clean_text(suggestion.get("keyword")),
            "normalized_keyword": self._clean_text(suggestion.get("normalized_keyword")),
            "weight": max(1, min(weight, 10)),
            "reason": self._clean_text(suggestion.get("reason")) or "Suggested by OpenAI.",
        }

    def _safe_question(self, question: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": question.get("id"),
            "language": question.get("language"),
            "message_text": question.get("message_text"),
            "normalized_text": question.get("normalized_text"),
            "detected_intent_code": question.get("detected_intent_code"),
            "confidence": question.get("confidence"),
            "reason": question.get("reason"),
            "candidates": question.get("candidates") or [],
            "entities": question.get("entities") or [],
        }

    def _safe_intents(self, intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "intent_code": item.get("intent_code"),
                "intent_name": item.get("intent_name"),
                "description": item.get("description"),
                "next_action": item.get("next_action"),
                "required_slots": item.get("required_slots"),
                "optional_slots": item.get("optional_slots"),
            }
            for item in intents
        ]

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _system_prompt(self) -> str:
        return (
            "You are helping an Indonesian ISP customer-service chatbot learn native intents. "
            "Recommend a reviewable mapping for one unresolved customer message. "
            "Choose only from available_intents. Do not invent answers or policies. "
            "Prefer sample utterance for short/contextual messages, keyword for strong reusable terms, "
            "both when the full message and a reusable keyword are useful, and ignore for out-of-scope messages. "
            "Normalize slang/salutations out of normalized_keyword. Keep reason concise in Indonesian."
        )

    def _schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent_code": {"type": "string"},
                "mapping_type": {
                    "type": "string",
                    "enum": ["sample", "keyword", "both", "ignore"],
                },
                "keyword": {"type": ["string", "null"]},
                "normalized_keyword": {"type": ["string", "null"]},
                "weight": {"type": "integer", "minimum": 1, "maximum": 10},
                "reason": {"type": "string"},
            },
            "required": [
                "intent_code",
                "mapping_type",
                "keyword",
                "normalized_keyword",
                "weight",
                "reason",
            ],
        }
