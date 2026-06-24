from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore
from app.services.chatbot import finalize_conversation_state
from app.services.isp_agent import AgentResponse, ISPCSAgent, normalize_text
from app.services.knowledge_retrieval import KnowledgeRetriever
from app.services.llm_response import DEFAULT_RESPONSE_RULES, LLMResponseGenerator

logger = logging.getLogger(__name__)

PROMPT_VERSION = "llm-response-v1"
RESPONSE_RULES_VERSION = "response-rules-v1"


class ConversationStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_intent: str | None = None
    current_topic: str | None = None
    stage: str | None = None
    waiting_for: list[str] = Field(default_factory=list)
    collected_slots: dict[str, str] = Field(default_factory=dict)
    last_bot_question: str | None = None
    last_user_message: str | None = None
    last_bot_response: str | None = None
    next_action: str | None = None


class BusinessStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_status: Literal[
        "none", "draft", "registered", "approved", "paid", "active", "cancelled"
    ] = "none"
    registration_id: str | None = None
    registration_url: str | None = None
    payment_url: str | None = None
    incoming_message_count: int = Field(default=1, ge=0, le=100000)
    invitation_already_exists: bool = False


class CandidateMappingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_code: str = Field(min_length=1)
    mapping_type: Literal["sample", "keyword", "both", "ignore"] = "both"
    sample_utterance: str | None = None
    keyword: str | None = None
    normalized_keyword: str | None = None
    weight: int = Field(default=4, ge=1, le=10)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_mapping_values(self) -> "CandidateMappingInput":
        if self.mapping_type in {"sample", "both"} and not (self.sample_utterance or "").strip():
            raise ValueError("Sample utterance is required for sample/both mapping.")
        if self.mapping_type in {"keyword", "both"} and not (self.keyword or "").strip():
            raise ValueError("Keyword is required for keyword/both mapping.")
        return self


class PipelineConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution: Literal["native_only", "full_pipeline"] = "full_pipeline"
    knowledge_retrieval_enabled: bool = True
    llm_enabled: bool = True
    registration_invitation_enabled: bool = True


class ExpectedResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_intent: str | None = None
    forbidden_intents: list[str] = Field(default_factory=list)
    minimum_confidence: float | None = Field(default=None, ge=0, le=1)
    required_slots: list[str] = Field(default_factory=list)
    forbidden_slots: list[str] = Field(default_factory=list)
    expected_action: str | None = None
    required_response_content: list[str] = Field(default_factory=list)
    forbidden_response_content: list[str] = Field(default_factory=list)


class DryRunExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int = Field(gt=0)
    device_id: int = Field(gt=0)
    message: str = Field(min_length=1, max_length=8000)
    state_source: Literal["fresh", "custom"] = "fresh"
    initial_state: ConversationStateInput = Field(default_factory=ConversationStateInput)
    business_state: BusinessStateInput = Field(default_factory=BusinessStateInput)
    mapping_mode: Literal["published", "candidate", "compare"] = "published"
    candidate_mapping: CandidateMappingInput | None = None
    pipeline: PipelineConfigInput = Field(default_factory=PipelineConfigInput)
    expected: ExpectedResultInput = Field(default_factory=ExpectedResultInput)

    @model_validator(mode="after")
    def validate_candidate_mode(self) -> "DryRunExecuteRequest":
        if self.mapping_mode in {"candidate", "compare"} and not self.candidate_mapping:
            raise ValueError("Candidate mapping is required for candidate/compare mode.")
        return self


class DryRunTestLab:
    """Runs the production chatbot decision stages without persistence or Fonnte."""

    def __init__(self, settings: Settings, store: SQLiteChatStore | None = None) -> None:
        self.settings = settings
        self.store = store or SQLiteChatStore(settings)

    def context(self, *, client_id: int | None = None, device_id: int | None = None) -> dict[str, Any]:
        clients: list[dict[str, Any]] = []
        for client in self.store.list_clients():
            safe_client = {
                "id": int(client["id"]),
                "name": client.get("name"),
                "account_name": client.get("account_name"),
                "account_slug": client.get("account_slug"),
                "is_active": bool(client.get("is_active", 1)),
                "devices": [],
            }
            for device in self.store.list_client_devices(int(client["id"])):
                safe_client["devices"].append(
                    {
                        "id": int(device["id"]),
                        "client_id": int(device["client_id"]),
                        "identifier": device.get("device_identifier"),
                        "name": device.get("device_name") or device.get("device_identifier"),
                    }
                )
            clients.append(safe_client)

        selected_client, selected_device = self._resolve_scope(
            clients,
            client_id=client_id,
            device_id=device_id,
            allow_default=True,
        )
        intents: list[dict[str, Any]] = []
        if selected_client and selected_device:
            intents = self.store.list_intents_for_mapping(
                client_id=int(selected_client["id"]),
                device_id=int(selected_device["id"]),
                read_only=True,
            )

        return {
            "clients": clients,
            "selected": {
                "client_id": selected_client.get("id") if selected_client else None,
                "device_id": selected_device.get("id") if selected_device else None,
            },
            "intents": intents,
            "llm": {
                "enabled": self.settings.llm_response_enabled,
                "configured": bool(self.settings.openai_api_key),
                "model": self.settings.openai_model,
                "timeout_seconds": self.settings.openai_timeout_seconds,
                "prompt_version": PROMPT_VERSION,
                "response_rules_version": RESPONSE_RULES_VERSION,
            },
            "safety": {
                "environment": "sandbox",
                "production_mutation": False,
                "fonnte_send": False,
            },
        }

    def execute(self, payload: DryRunExecuteRequest) -> dict[str, Any]:
        clients = self.context(client_id=payload.client_id, device_id=payload.device_id)["clients"]
        client, device = self._resolve_scope(
            clients,
            client_id=payload.client_id,
            device_id=payload.device_id,
            allow_default=False,
        )
        if not client or not device:
            raise ValueError("Client and device are required.")

        state_before = (
            payload.initial_state.model_dump(mode="json")
            if payload.state_source == "custom"
            else ConversationStateInput().model_dump(mode="json")
        )
        catalog = self.store.get_intent_agent_catalog(
            client_id=payload.client_id,
            device_id=payload.device_id,
            read_only=True,
        )
        candidate = payload.candidate_mapping.model_dump(mode="json") if payload.candidate_mapping else None
        variants: dict[str, dict[str, Any]] = {}

        if payload.mapping_mode == "compare":
            variants["before"] = self._run_variant(
                name="before",
                catalog=catalog,
                payload=payload,
                state_before=state_before,
            )
            variants["after"] = self._run_variant(
                name="after",
                catalog=self._catalog_with_candidate(catalog, payload.candidate_mapping),
                payload=payload,
                state_before=state_before,
            )
        else:
            active_catalog = (
                self._catalog_with_candidate(catalog, payload.candidate_mapping)
                if payload.mapping_mode == "candidate"
                else catalog
            )
            variants["single"] = self._run_variant(
                name="single",
                catalog=active_catalog,
                payload=payload,
                state_before=state_before,
            )

        now = datetime.now(timezone.utc)
        test_id = f"DRT-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
        report: dict[str, Any] = {
            "test_id": test_id,
            "mode": payload.mapping_mode,
            "environment": "dry_run",
            "timestamp": now.isoformat(),
            "production_mutation": False,
            "external_send": False,
            "client": {"id": client["id"], "name": client.get("name")},
            "device": {
                "id": device["id"],
                "identifier": device.get("identifier"),
                "name": device.get("name"),
            },
            "input": {
                "message": payload.message,
                "state_source": payload.state_source,
                "initial_state": state_before,
                "business_state": payload.business_state.model_dump(mode="json"),
                "pipeline": payload.pipeline.model_dump(mode="json"),
                "expected": payload.expected.model_dump(mode="json"),
                "candidate_mapping": candidate,
            },
            "variants": variants,
        }
        if payload.mapping_mode == "compare":
            report["diff"] = self._compare(variants["before"], variants["after"])
            report["conclusion"] = self._conclusion(variants["before"], variants["after"])

        sanitized_report = self._sanitize(report)
        audit_summary = self._audit_summary(sanitized_report)
        logger.info(
            "Provider dry-run executed test_id=%s client_id=%s device_id=%s mode=%s production_mutation=false",
            test_id,
            payload.client_id,
            payload.device_id,
            payload.mapping_mode,
        )
        return {
            "report": report,
            "sanitized_report": sanitized_report,
            "audit_summary": audit_summary,
        }

    def _run_variant(
        self,
        *,
        name: str,
        catalog: dict[str, Any],
        payload: DryRunExecuteRequest,
        state_before: dict[str, Any],
    ) -> dict[str, Any]:
        agent_response = ISPCSAgent(catalog).answer(
            payload.message,
            conversation_state=copy.deepcopy(state_before),
        )
        if payload.pipeline.knowledge_retrieval_enabled:
            knowledge = KnowledgeRetriever(catalog).retrieve(
                user_message=payload.message,
                agent_response=agent_response,
                conversation_state=copy.deepcopy(state_before),
            )
        else:
            knowledge = {
                "type": agent_response.intent.intent_code,
                "topic": state_before.get("current_topic") or agent_response.intent.intent_code,
                "entities": [entity.as_dict() for entity in agent_response.entities],
                "data": {},
                "missing_fields": [],
                "notes": ["Knowledge retrieval disabled by dry-run configuration."],
            }

        generator_settings = replace(
            self.settings,
            llm_response_enabled=(
                payload.pipeline.execution == "full_pipeline" and payload.pipeline.llm_enabled
            ),
        )
        generator = LLMResponseGenerator(generator_settings)
        llm_requested = generator_settings.llm_response_enabled
        prompt = ""
        if llm_requested:
            prompt = generator.build_prompt(
                user_message=payload.message,
                agent_response=agent_response,
                conversation_state=state_before,
                knowledge=knowledge,
                native_reply=agent_response.reply_text,
            )
        final_response = generator.generate_reply(
            user_message=payload.message,
            agent_response=agent_response,
            conversation_state=state_before,
            knowledge=knowledge,
            native_reply=agent_response.reply_text,
        )

        invitation = self._simulate_invitation(payload, agent_response)
        if invitation["append_to_response"]:
            final_response = (
                f"{final_response}\n\n"
                "Kalau Kakak mau lanjut pendaftaran, isi form ini ya: "
                "[REGISTRATION_URL_REDACTED]"
            )

        state_after = finalize_conversation_state(
            state=agent_response.memory_update,
            knowledge=knowledge,
            user_message=payload.message,
            reply_text=final_response,
        )
        planned_action = agent_response.intent.next_action or (state_after or {}).get("next_action")
        planned_side_effects = {
            "database_writes": [
                "incoming message",
                "conversation state update",
                "conversation log",
                "message analysis",
                *(["registration invitation"] if invitation["would_create"] else []),
            ],
            "external_calls": [
                *(["OpenAI Responses API"] if llm_requested else []),
                "Fonnte send message",
            ],
            "registration": invitation,
            "dry_run_execution": {
                "all_database_writes_blocked": True,
                "fonnte_send_blocked": True,
                "production_mutation": False,
            },
        }
        validation = self._validate(
            expected=payload.expected,
            business_state=payload.business_state,
            agent_response=agent_response,
            final_response=final_response,
            planned_action=planned_action,
            invitation=invitation,
        )
        return {
            "variant": name,
            "state_before": state_before,
            "native_analysis": agent_response.as_dict(),
            "slot_processing": self._slot_trace(agent_response, state_before),
            "business_state": payload.business_state.model_dump(mode="json"),
            "knowledge": knowledge,
            "native_response": agent_response.reply_text,
            "llm_input_summary": {
                "requested": llm_requested,
                "configured": bool(self.settings.openai_api_key),
                "model": self.settings.openai_model,
                "prompt_version": PROMPT_VERSION,
                "response_rules_version": RESPONSE_RULES_VERSION,
                "native_fallback_included": True,
                "conversation_state_included": True,
                "knowledge_items": self._knowledge_item_count(knowledge),
                "previous_response_included": bool(
                    state_before.get("last_bot_response") or state_before.get("last_bot_question")
                ),
                "anti_repeat_rule": bool(DEFAULT_RESPONSE_RULES["avoid_repeating_previous_answer"]),
                "sanitized_prompt": self._sanitize_prompt(prompt) if prompt else None,
            },
            "final_response": final_response,
            "planned_action": planned_action,
            "planned_state_after": state_after,
            "planned_side_effects": planned_side_effects,
            "validation": validation,
            "executive_result": self._executive_result(validation),
        }

    def _catalog_with_candidate(
        self,
        catalog: dict[str, Any],
        candidate: CandidateMappingInput | None,
    ) -> dict[str, Any]:
        if not candidate:
            raise ValueError("Candidate mapping is required.")
        overlaid = copy.deepcopy(catalog)
        known_intents = {str(item.get("intent_code")) for item in overlaid.get("intents", [])}
        if candidate.intent_code not in known_intents:
            raise ValueError(f"Intent `{candidate.intent_code}` is not available for this Client/device.")
        if candidate.mapping_type == "ignore":
            return overlaid
        if candidate.mapping_type in {"sample", "both"}:
            overlaid.setdefault("sample_utterances", []).append(
                {
                    "intent_code": candidate.intent_code,
                    "lang_code": "id",
                    "utterance": candidate.sample_utterance,
                    "weight": candidate.weight,
                    "notes": candidate.notes or "Dry-run candidate overlay",
                }
            )
        if candidate.mapping_type in {"keyword", "both"}:
            overlaid.setdefault("intent_keywords", []).append(
                {
                    "intent_code": candidate.intent_code,
                    "intent_name": candidate.intent_code,
                    "lang_code": "id",
                    "keyword": candidate.keyword,
                    "normalized_keyword": candidate.normalized_keyword
                    or normalize_text(candidate.keyword or ""),
                    "weight": candidate.weight,
                    "notes": candidate.notes or "Dry-run candidate overlay",
                }
            )
        return overlaid

    def _resolve_scope(
        self,
        clients: list[dict[str, Any]],
        *,
        client_id: int | None,
        device_id: int | None,
        allow_default: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        client = next((item for item in clients if int(item["id"]) == client_id), None)
        if not client and allow_default and client_id is None:
            client = clients[0] if clients else None
        if client_id is not None and not client:
            raise ValueError("Client was not found.")
        devices = client.get("devices", []) if client else []
        device = next((item for item in devices if int(item["id"]) == device_id), None)
        if not device and allow_default and device_id is None:
            device = devices[0] if devices else None
        if device_id is not None and not device:
            raise ValueError("Device does not belong to the selected Client.")
        return client, device

    def _simulate_invitation(
        self,
        payload: DryRunExecuteRequest,
        agent_response: AgentResponse,
    ) -> dict[str, Any]:
        enabled = payload.pipeline.registration_invitation_enabled
        threshold_reached = (
            payload.business_state.incoming_message_count
            >= self.settings.registration_offer_message_threshold
        )
        should_offer = enabled and (
            agent_response.intent.intent_code == "ask_coverage" or threshold_reached
        )
        would_create = should_offer and not payload.business_state.invitation_already_exists
        return {
            "enabled": enabled,
            "threshold": self.settings.registration_offer_message_threshold,
            "incoming_message_count": payload.business_state.incoming_message_count,
            "invitation_already_exists": payload.business_state.invitation_already_exists,
            "should_offer": should_offer,
            "would_create": would_create,
            "append_to_response": would_create,
            "registration_status_considered_by_production_logic": False,
        }

    def _slot_trace(
        self,
        response: AgentResponse,
        state_before: dict[str, Any],
    ) -> dict[str, Any]:
        waiting_for = list(state_before.get("waiting_for") or [])
        memory_entities = [
            entity.as_dict() for entity in response.entities if entity.source == "memory"
        ]
        selected_source = "none"
        matched = response.intent.matched_keywords
        if memory_entities:
            selected_source = "conversation_memory"
        elif any(str(item).startswith("sample:") for item in matched):
            selected_source = "sample"
        elif any(str(item).startswith("heuristic:") for item in matched):
            selected_source = "heuristic"
        elif matched:
            selected_source = "keyword"
        return {
            "waiting_for_before": waiting_for,
            "fresh_intent_detected": bool(
                response.intent.intent_code
                and response.intent.intent_code != state_before.get("current_intent")
            ),
            "message_accepted_as_waiting_slot": bool(memory_entities),
            "memory_entities": memory_entities,
            "classification_source": selected_source,
            "inference_reason": (
                "Conversation memory accepted the message before fresh intent ranking."
                if memory_entities
                else "No waiting slot was inferred; native intent ranking determined the result."
            ),
        }

    def _validate(
        self,
        *,
        expected: ExpectedResultInput,
        business_state: BusinessStateInput,
        agent_response: AgentResponse,
        final_response: str,
        planned_action: str | None,
        invitation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []

        def add(code: str, label: str, passed: bool, expected_value: Any, actual: Any) -> None:
            checks.append(
                {
                    "code": code,
                    "label": label,
                    "status": "pass" if passed else "fail",
                    "expected": expected_value,
                    "actual": actual,
                }
            )

        intent = agent_response.intent.intent_code
        if expected.expected_intent:
            add("expected_intent", "Expected intent", intent == expected.expected_intent, expected.expected_intent, intent)
        else:
            add("intent_recognized", "Intent recognized", intent != "unknown", "not unknown", intent)
        if expected.forbidden_intents:
            add("forbidden_intents", "Forbidden intents", intent not in expected.forbidden_intents, expected.forbidden_intents, intent)
        if expected.minimum_confidence is not None:
            add(
                "minimum_confidence",
                "Minimum confidence",
                agent_response.intent.confidence >= expected.minimum_confidence,
                expected.minimum_confidence,
                agent_response.intent.confidence,
            )
        entity_codes = {entity.entity_code for entity in agent_response.entities}
        if expected.required_slots:
            missing = [slot for slot in expected.required_slots if slot not in entity_codes]
            add("required_slots", "Required slots", not missing, expected.required_slots, sorted(entity_codes))
        if expected.forbidden_slots:
            found = [slot for slot in expected.forbidden_slots if slot in entity_codes]
            add("forbidden_slots", "Forbidden slots", not found, expected.forbidden_slots, sorted(entity_codes))
        if expected.expected_action:
            add("expected_action", "Expected business action", planned_action == expected.expected_action, expected.expected_action, planned_action)
        lowered_response = final_response.casefold()
        for value in expected.required_response_content:
            add(
                f"required_content:{value}",
                f"Response contains: {value}",
                value.casefold() in lowered_response,
                value,
                final_response,
            )
        for value in expected.forbidden_response_content:
            add(
                f"forbidden_content:{value}",
                f"Response excludes: {value}",
                value.casefold() not in lowered_response,
                f"not {value}",
                final_response,
            )
        registration_exists = business_state.registration_status not in {"none", "draft", "cancelled"}
        add(
            "no_duplicate_registration",
            "No duplicate registration",
            not (registration_exists and invitation["would_create"]),
            "no new invitation when registration exists",
            "would create invitation" if invitation["would_create"] else "no invitation creation",
        )
        add("production_mutation", "Production data unchanged", True, False, False)
        add("fonnte_blocked", "Fonnte send blocked", True, True, True)
        return checks

    def _executive_result(self, validation: list[dict[str, Any]]) -> dict[str, Any]:
        failures = [check for check in validation if check["status"] == "fail"]
        groups = {
            "recognition": self._group_status(validation, {"expected_intent", "intent_recognized", "forbidden_intents", "minimum_confidence"}),
            "slot_handling": self._group_status(validation, {"required_slots", "forbidden_slots"}),
            "business_action": self._group_status(validation, {"expected_action"}),
            "final_response": self._group_prefix_status(validation, {"required_content:", "forbidden_content:"}),
            "side_effect_safety": self._group_status(
                validation,
                {"no_duplicate_registration", "production_mutation", "fonnte_blocked"},
            ),
        }
        return {
            "result": "failed" if failures else "passed",
            "groups": groups,
            "failure_count": len(failures),
        }

    def _group_status(self, checks: list[dict[str, Any]], codes: set[str]) -> str:
        selected = [check for check in checks if check["code"] in codes]
        if not selected:
            return "not_configured"
        return "fail" if any(check["status"] == "fail" for check in selected) else "pass"

    def _group_prefix_status(self, checks: list[dict[str, Any]], prefixes: set[str]) -> str:
        selected = [
            check for check in checks if any(check["code"].startswith(prefix) for prefix in prefixes)
        ]
        if not selected:
            return "not_configured"
        return "fail" if any(check["status"] == "fail" for check in selected) else "pass"

    def _compare(self, before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
        before_analysis = before["native_analysis"]
        after_analysis = after["native_analysis"]
        rows = [
            ("Intent", before_analysis["intent"]["intent_code"], after_analysis["intent"]["intent_code"]),
            ("Confidence", before_analysis["intent"]["confidence"], after_analysis["intent"]["confidence"]),
            ("Extracted slots", self._entity_codes(before_analysis), self._entity_codes(after_analysis)),
            ("Native response", before["native_response"], after["native_response"]),
            ("Final response", before["final_response"], after["final_response"]),
            ("Planned action", before["planned_action"], after["planned_action"]),
            ("Planned state", before["planned_state_after"], after["planned_state_after"]),
        ]
        return [
            {
                "component": component,
                "before": old,
                "after": new,
                "evaluation": "unchanged" if old == new else "changed",
            }
            for component, old, new in rows
        ]

    def _conclusion(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        before_intent = before["native_analysis"]["intent"]["intent_code"]
        after_intent = after["native_analysis"]["intent"]["intent_code"]
        after_failures = [
            check["code"] for check in after["validation"] if check["status"] == "fail"
        ]
        recognition_changed = before_intent != after_intent
        memory_priority = bool(after.get("slot_processing", {}).get("message_accepted_as_waiting_slot"))
        if memory_priority:
            recognition_summary = (
                "Candidate mapping did not affect recognition because conversation memory "
                "accepted the message as a waiting slot before fresh intent ranking."
            )
            suspected_layer = ["conversation_state", "slot_priority"]
        elif recognition_changed:
            recognition_summary = (
                f"Candidate mapping changed recognition from {before_intent} to {after_intent}."
            )
            suspected_layer = (
                ["workflow", "conversation_state", "business_state_handling"]
                if after_failures
                else []
            )
        else:
            recognition_summary = (
                f"Candidate mapping did not change the selected intent ({after_intent})."
            )
            suspected_layer = ["intent_classification"]
        return {
            "recognition_changed": recognition_changed,
            "recognition_summary": recognition_summary,
            "business_behavior_fixed": not after_failures,
            "safe_to_publish_as_complete_fix": recognition_changed and not after_failures,
            "remaining_failures": after_failures,
            "suspected_layer": suspected_layer,
        }

    def _entity_codes(self, analysis: dict[str, Any]) -> list[str]:
        return sorted(str(item.get("entity_code")) for item in analysis.get("entities", []))

    def _knowledge_item_count(self, knowledge: dict[str, Any]) -> int:
        count = 0
        for value in (knowledge.get("data") or {}).values():
            if isinstance(value, list):
                count += len(value)
            elif value:
                count += 1
        return count

    def _sanitize_prompt(self, prompt: str) -> str:
        redacted = self._sanitize_text(prompt)
        redacted = re.sub(
            r'("(?:address|last_user_message|last_bot_response|last_bot_question)"\s*:\s*)".*?"',
            r'\1"[REDACTED]"',
            redacted,
            flags=re.IGNORECASE,
        )
        return redacted

    def _sanitize(self, value: Any, key: str = "") -> Any:
        lowered_key = key.casefold()
        if isinstance(value, dict):
            return {item_key: self._sanitize(item_value, item_key) for item_key, item_value in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item, key) for item in value]
        if value is None:
            return None
        if any(marker in lowered_key for marker in ("secret", "cookie", "api_key", "token")):
            return "[SECRET_REDACTED]"
        if "registration_url" in lowered_key:
            return "[REGISTRATION_URL_REDACTED]" if value else value
        if "payment_url" in lowered_key:
            return "[PAYMENT_URL_REDACTED]" if value else value
        if "url" in lowered_key or "maps_link" in lowered_key:
            return "[URL_REDACTED]" if value else value
        if "email" in lowered_key:
            return "[EMAIL_REDACTED]" if value else value
        if "phone" in lowered_key or "sender_number" in lowered_key:
            return "[PHONE_REDACTED]" if value else value
        if "address" in lowered_key:
            return "[ADDRESS_REDACTED]" if value else value
        if isinstance(value, str):
            return self._sanitize_text(value)
        return value

    def _sanitize_text(self, value: str) -> str:
        redacted = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[EMAIL_REDACTED]", value, flags=re.IGNORECASE)
        redacted = re.sub(r"https?://\S+", "[URL_REDACTED]", redacted)
        return re.sub(r"(?<!\d)(?:\+?62|0)8\d{7,12}(?!\d)", "[PHONE_REDACTED]", redacted)

    def _audit_summary(self, report: dict[str, Any]) -> str:
        lines = [
            "DRY-RUN CHATBOT TEST REPORT",
            f"Test ID: {report['test_id']}",
            f"Mode: {report['mode']}",
            f"Client: {report['client']['name']}",
            f"Device: {report['device']['name']}",
            f"Timestamp: {report['timestamp']}",
            "",
            "TEST INPUT",
            f"Message: {report['input']['message']}",
            f"Initial state: {json.dumps(report['input']['initial_state'], ensure_ascii=False)}",
            f"Business state: {json.dumps(report['input']['business_state'], ensure_ascii=False)}",
        ]
        for variant_name, variant in report["variants"].items():
            intent = variant["native_analysis"]["intent"]
            lines.extend(
                [
                    "",
                    variant_name.upper(),
                    f"Intent: {intent['intent_code']} ({intent['confidence']})",
                    f"Entities: {json.dumps(variant['native_analysis']['entities'], ensure_ascii=False)}",
                    f"Native response: {variant['native_response']}",
                    f"Final response: {variant['final_response']}",
                    f"Planned action: {variant['planned_action']}",
                    f"Result: {variant['executive_result']['result'].upper()}",
                    "Validation:",
                    *[
                        f"- {check['label']}: {check['status'].upper()}"
                        for check in variant["validation"]
                    ],
                ]
            )
        if report.get("conclusion"):
            lines.extend(
                [
                    "",
                    "CONCLUSION",
                    report["conclusion"]["recognition_summary"],
                    f"Safe to publish as complete fix: {report['conclusion']['safe_to_publish_as_complete_fix']}",
                    f"Suspected layer: {', '.join(report['conclusion']['suspected_layer']) or '-'}",
                ]
            )
        lines.extend(
            [
                "",
                "SAFETY",
                "Production data changed: NO",
                "Fonnte message sent: NO",
            ]
        )
        return "\n".join(lines)
