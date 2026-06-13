from __future__ import annotations

import re
from typing import Any

from app.services.isp_agent import AgentResponse, normalize_text


class KnowledgeRetriever:
    def __init__(self, catalog: dict[str, Any]) -> None:
        self.packages = catalog.get("internet_packages", [])
        self.coverage_areas = catalog.get("coverage_areas", [])
        self.payment_methods = catalog.get("payment_methods", [])

    def retrieve(
        self,
        *,
        user_message: str,
        agent_response: AgentResponse,
        conversation_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        intent_code = agent_response.intent.intent_code
        entities = [entity.as_dict() for entity in agent_response.entities]
        state = conversation_state or {}

        payload: dict[str, Any] = {
            "type": intent_code,
            "topic": self._topic_for_intent(intent_code, state),
            "entities": entities,
            "data": {},
            "missing_fields": [],
            "notes": [],
        }

        if intent_code in {"ask_package", "ask_price", "ask_installation_fee", "compare_package", "choose_package"}:
            payload["data"]["packages"] = self._matching_packages(entities, state)
            if not payload["data"]["packages"]:
                payload["missing_fields"].append("package_catalog")

        if intent_code in {"ask_coverage", "provide_address"} or payload["topic"] == "coverage_check":
            area = self._area_context(entities, state)
            payload["data"]["coverage"] = self._coverage_payload(area)
            if not area:
                payload["missing_fields"].append("area")

        if intent_code == "ask_payment_method" or payload["topic"] == "payment":
            method = self._payment_method_context(entities, user_message)
            payload["data"]["payment_methods"] = self._payment_payload(method)

        return payload

    def _matching_packages(
        self,
        entities: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        packages = [
            package
            for package in self.packages
            if int(package.get("is_active", 1) or 0) == 1
        ]
        speed = self._speed_context(entities, state)
        if speed:
            by_speed = [
                package
                for package in packages
                if int(package.get("speed_mbps") or 0) == speed
            ]
            if by_speed:
                packages = by_speed

        area = self._area_context(entities, state)
        if area:
            by_area = [
                package
                for package in packages
                if self._package_covers_area(package, area)
            ]
            if by_area:
                packages = by_area
        return packages

    def _coverage_payload(self, area: str | None) -> dict[str, Any]:
        if not area:
            return {"area": None, "coverage_status": "unknown", "matched_area": None}
        matched = self._find_coverage_area(area)
        if not matched:
            return {"area": area, "coverage_status": "unknown", "matched_area": None}
        return {
            "area": area,
            "coverage_status": matched.get("coverage_status") or "unknown",
            "matched_area": matched,
        }

    def _payment_payload(self, method: str | None) -> list[dict[str, Any]]:
        methods = list(self.payment_methods)
        if method:
            matched = self._find_payment_method(method)
            return [matched] if matched else []
        return methods

    def _topic_for_intent(self, intent_code: str, state: dict[str, Any]) -> str:
        if state.get("current_topic"):
            return str(state["current_topic"])
        return {
            "ask_package": "package_info",
            "ask_price": "package_info",
            "compare_package": "package_info",
            "choose_package": "order_confirmation",
            "confirm_order": "order_confirmation",
            "ask_coverage": "coverage_check",
            "provide_address": "coverage_check",
            "ask_payment_method": "payment",
            "ask_installation_schedule": "installation_schedule",
        }.get(intent_code, intent_code)

    def _area_context(self, entities: list[dict[str, Any]], state: dict[str, Any]) -> str | None:
        for entity in entities:
            if entity.get("entity_code") in {"area", "address"} and str(entity.get("value") or "").strip():
                return str(entity["value"]).strip()
        slots = state.get("collected_slots") or {}
        if isinstance(slots, dict):
            for key in ("area", "address", "district", "city", "location"):
                if str(slots.get(key) or "").strip():
                    return str(slots[key]).strip()
        return None

    def _speed_context(self, entities: list[dict[str, Any]], state: dict[str, Any]) -> int | None:
        for entity in entities:
            if entity.get("entity_code") == "speed":
                match = re.search(r"\d+", str(entity.get("value") or ""))
                if match:
                    return int(match.group(0))
        slots = state.get("collected_slots") or {}
        if isinstance(slots, dict):
            for key in ("speed", "selected_speed_mbps"):
                match = re.search(r"\d+", str(slots.get(key) or ""))
                if match:
                    return int(match.group(0))
        return None

    def _payment_method_context(
        self,
        entities: list[dict[str, Any]],
        user_message: str,
    ) -> str | None:
        for entity in entities:
            if entity.get("entity_code") == "payment_method" and str(entity.get("value") or "").strip():
                return str(entity["value"]).strip()
        normalized = normalize_text(user_message)
        for marker in ("qris", "transfer", "cash", "tunai", "ewallet", "e wallet", "wallet"):
            if re.search(rf"\b{re.escape(marker)}\b", normalized):
                return marker
        return None

    def _package_covers_area(self, package: dict[str, Any], area: str) -> bool:
        normalized_area = normalize_text(area)
        for package_area in package.get("areas") or []:
            normalized_package_area = normalize_text(str(package_area))
            if normalized_package_area and (
                normalized_package_area in normalized_area
                or normalized_area in normalized_package_area
            ):
                return True
        return False

    def _find_coverage_area(self, area: str) -> dict[str, Any] | None:
        normalized_area = normalize_text(area)
        for item in self.coverage_areas:
            for key in ("area_name", "city", "district", "area_code"):
                normalized_candidate = normalize_text(str(item.get(key) or ""))
                if normalized_candidate and (
                    normalized_candidate in normalized_area
                    or normalized_area in normalized_candidate
                ):
                    return item
        return None

    def _find_payment_method(self, method: str) -> dict[str, Any] | None:
        normalized = normalize_text(method)
        aliases = {
            "transfer": "bank_transfer",
            "transfer bank": "bank_transfer",
            "bank transfer": "bank_transfer",
            "qris": "qris",
            "cash": "cash",
            "tunai": "cash",
            "ewallet": "ewallet",
            "e wallet": "ewallet",
            "wallet": "ewallet",
        }
        code = aliases.get(normalized, normalized.replace(" ", "_"))
        for item in self.payment_methods:
            if item.get("method_code") == code:
                return item
            if normalize_text(str(item.get("method_name") or "")) == normalized:
                return item
        return None
