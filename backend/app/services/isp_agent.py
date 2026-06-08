from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


@dataclass(frozen=True)
class IntentMatch:
    intent_code: str
    intent_name: str
    score: int
    confidence: float
    matched_keywords: list[str]
    next_action: str | None
    required_slots: list[str]
    optional_slots: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_code": self.intent_code,
            "intent_name": self.intent_name,
            "score": self.score,
            "confidence": self.confidence,
            "matched_keywords": self.matched_keywords,
            "next_action": self.next_action,
            "required_slots": self.required_slots,
            "optional_slots": self.optional_slots,
        }


@dataclass(frozen=True)
class EntityMatch:
    entity_code: str
    entity_name: str
    value: str
    normalized_value: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "entity_code": self.entity_code,
            "entity_name": self.entity_name,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "source": self.source,
        }


@dataclass(frozen=True)
class AgentResponse:
    language: str
    intent: IntentMatch
    candidates: list[IntentMatch]
    entities: list[EntityMatch]
    missing_slots: list[str]
    reply_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "intent": self.intent.as_dict(),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "entities": [entity.as_dict() for entity in self.entities],
            "missing_slots": self.missing_slots,
            "reply_text": self.reply_text,
        }


class ISPCSAgent:
    def __init__(self, catalog: dict[str, Any]) -> None:
        self.intent_names = {
            item["intent_code"]: item["intent_name"]
            for item in catalog.get("intents", [])
        }
        self.intent_keywords = catalog.get("intent_keywords", [])
        self.entity_keywords = catalog.get("entity_keywords", [])
        self.normalization_rules = catalog.get("normalization_rules", [])
        self.intent_mappings = {
            item["intent_code"]: self._decode_mapping(item)
            for item in catalog.get("intent_mappings", [])
        }

    def answer(self, message_text: str) -> AgentResponse:
        normalized_by_lang = self._normalize_by_language(message_text)
        language = self._detect_language(normalized_by_lang)
        normalized_message = normalized_by_lang[language]
        candidates = self._rank_intents(normalized_message, language)
        intent = candidates[0] if candidates else self._unknown_intent()
        entities = self._extract_entities(message_text, normalized_message, language)
        missing_slots = self._missing_slots(intent.required_slots, entities)
        reply_text = self._compose_reply(intent, entities, missing_slots)

        return AgentResponse(
            language=language,
            intent=intent,
            candidates=candidates[:5],
            entities=entities,
            missing_slots=missing_slots,
            reply_text=reply_text,
        )

    def _normalize_by_language(self, message_text: str) -> dict[str, str]:
        base = normalize_text(message_text)
        languages = {
            str(rule["lang_code"])
            for rule in self.normalization_rules
            if rule.get("lang_code")
        } or {"id"}
        normalized = {lang_code: base for lang_code in languages}
        for rule in self.normalization_rules:
            lang_code = str(rule["lang_code"])
            source = normalize_text(str(rule["source_text"]))
            replacement = normalize_text(str(rule["normalized_text"]))
            if not source or not replacement:
                continue
            normalized[lang_code] = re.sub(
                rf"\b{re.escape(source)}\b",
                replacement,
                normalized.get(lang_code, base),
            )
        return normalized

    def _detect_language(self, normalized_by_lang: dict[str, str]) -> str:
        scores = {lang_code: 0 for lang_code in normalized_by_lang}
        for keyword in self.intent_keywords:
            lang_code = str(keyword["lang_code"])
            normalized_message = normalized_by_lang.get(lang_code)
            if not normalized_message:
                continue
            phrase = normalize_text(
                str(keyword.get("normalized_keyword") or keyword.get("keyword") or "")
            )
            if phrase and phrase in normalized_message:
                scores[lang_code] = scores.get(lang_code, 0) + int(keyword.get("weight") or 1)
        best_lang, best_score = max(scores.items(), key=lambda item: item[1])
        return best_lang if best_score > 0 else "id"

    def _rank_intents(self, normalized_message: str, language: str) -> list[IntentMatch]:
        scored: dict[str, dict[str, Any]] = {}
        message_tokens = set(normalized_message.split())
        for keyword in self.intent_keywords:
            if keyword["lang_code"] != language:
                continue

            phrase = normalize_text(
                str(keyword.get("normalized_keyword") or keyword.get("keyword") or "")
            )
            if not phrase:
                continue

            phrase_tokens = phrase.split()
            weight = int(keyword.get("weight") or 1)
            score = 0
            if phrase in normalized_message:
                score = weight * max(1, len(phrase_tokens))
            else:
                overlap = sum(token in message_tokens for token in phrase_tokens)
                if phrase_tokens and overlap == len(phrase_tokens):
                    score = weight
                elif len(phrase_tokens) > 2 and overlap >= 2:
                    score = max(1, weight // 2)

            if score == 0:
                continue

            intent_code = str(keyword["intent_code"])
            bucket = scored.setdefault(
                intent_code,
                {
                    "score": 0,
                    "keywords": [],
                },
            )
            bucket["score"] += score
            bucket["keywords"].append(str(keyword["keyword"]))

        candidates: list[IntentMatch] = []
        for intent_code, item in scored.items():
            mapping = self.intent_mappings.get(intent_code, {})
            score = int(item["score"])
            candidates.append(
                IntentMatch(
                    intent_code=intent_code,
                    intent_name=self.intent_names.get(intent_code, intent_code),
                    score=score,
                    confidence=round(min(0.99, score / 12), 2),
                    matched_keywords=list(dict.fromkeys(item["keywords"])),
                    next_action=mapping.get("next_action"),
                    required_slots=mapping.get("required_slots", []),
                    optional_slots=mapping.get("optional_slots", []),
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates or [self._unknown_intent()]

    def _extract_entities(
        self,
        message_text: str,
        normalized_message: str,
        language: str,
    ) -> list[EntityMatch]:
        entities: list[EntityMatch] = []
        seen: set[tuple[str, str]] = set()

        for keyword in self.entity_keywords:
            if keyword["lang_code"] != language:
                continue
            phrase = normalize_text(
                str(keyword.get("normalized_keyword") or keyword.get("keyword") or "")
            )
            raw_keyword = str(keyword.get("keyword") or phrase)
            if not phrase or phrase not in normalized_message:
                continue
            key = (str(keyword["entity_code"]), phrase)
            if key in seen:
                continue
            seen.add(key)
            entities.append(
                EntityMatch(
                    entity_code=str(keyword["entity_code"]),
                    entity_name=str(keyword["entity_name"]),
                    value=raw_keyword,
                    normalized_value=phrase,
                    source="keyword",
                )
            )

        entities.extend(self._extract_regex_entities(message_text, normalized_message, seen))
        return entities

    def _extract_regex_entities(
        self,
        message_text: str,
        normalized_message: str,
        seen: set[tuple[str, str]],
    ) -> list[EntityMatch]:
        entities: list[EntityMatch] = []
        patterns = (
            ("speed", "Kecepatan internet", r"\b\d+\s*(?:mbps|mega|gbps)\b"),
            ("phone_number", "Nomor HP", r"(?:\+?62|0)8\d{7,12}"),
            ("price", "Harga", r"\b(?:rp|idr)?\s?\d[\d.]{3,}\b"),
        )
        for entity_code, entity_name, pattern in patterns:
            for match in re.finditer(pattern, message_text.lower()):
                value = match.group(0).strip()
                normalized_value = normalize_text(value)
                key = (entity_code, normalized_value)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(
                    EntityMatch(
                        entity_code=entity_code,
                        entity_name=entity_name,
                        value=value,
                        normalized_value=normalized_value,
                        source="regex",
                    )
                )

        if any(marker in normalized_message for marker in ("alamat", "jalan", "jl", "komplek")):
            key = ("address", normalized_message)
            if key not in seen:
                entities.append(
                    EntityMatch(
                        entity_code="address",
                        entity_name="Alamat",
                        value=message_text.strip(),
                        normalized_value=normalized_message,
                        source="heuristic",
                    )
                )
        area_match = re.search(r"\b(?:di|daerah|lokasi|area)\s+([a-z0-9 ]{3,40})", normalized_message)
        if area_match:
            area = area_match.group(1).strip()
            area = re.split(
                r"\b(?:apakah|apa|bisa|sudah|tercover|coverage|jaringan|pasang|internet)\b",
                area,
                maxsplit=1,
            )[0].strip()
            key = ("area", area)
            if area and key not in seen:
                entities.append(
                    EntityMatch(
                        entity_code="area",
                        entity_name="Area/wilayah",
                        value=area,
                        normalized_value=area,
                        source="heuristic",
                    )
                )
        return entities

    def _missing_slots(self, required_slots: list[str], entities: list[EntityMatch]) -> list[str]:
        entity_codes = {entity.entity_code for entity in entities}
        return [slot for slot in required_slots if slot not in entity_codes]

    def _compose_reply(
        self,
        intent: IntentMatch,
        entities: list[EntityMatch],
        missing_slots: list[str],
    ) -> str:
        context = self._entity_context(entities)
        if missing_slots:
            return self._slot_prompt(intent, missing_slots, context)

        templates = {
            "show_package_list": (
                "Siap Kak, kami bantu info paket internet rumah. "
                "Boleh sebutkan kebutuhan utamanya: pemakaian ringan, keluarga, kerja dari rumah, atau gaming?"
            ),
            "show_price": (
                f"Siap Kak, saya bantu cek harga paket{context}. "
                "Untuk harga yang paling pas, boleh info area pemasangan atau alamat lengkapnya?"
            ),
            "ask_or_validate_address": (
                "Bisa Kak. Saya bantu cek coverage jaringan. Mohon kirim alamat lengkap "
                "beserta patokan terdekat agar tim bisa validasi area."
            ),
            "check_technician_schedule": (
                "Bisa kami bantu jadwalkan teknisi. Mohon kirim alamat lengkap, paket yang dipilih, "
                "dan preferensi waktu pemasangan."
            ),
            "show_payment_methods": (
                "Pembayaran bisa kami bantu arahkan sesuai kebijakan client: transfer bank, QRIS, "
                "cash, e-wallet, atau virtual account bila tersedia."
            ),
            "create_order": (
                "Baik Kak, data utama sudah cukup untuk diproses. Saya teruskan sebagai permintaan pemasangan."
            ),
            "ask_address_or_show_packages": (
                "Halo Kak, bisa kami bantu untuk pemasangan internet rumah. "
                "Boleh kirim alamat lengkap dulu untuk cek coverage, atau sebutkan paket/speed yang diminati."
            ),
        }
        if intent.intent_code in ("greeting", "thanks"):
            return "Halo Kak, terima kasih sudah menghubungi kami. Ada yang bisa saya bantu terkait internet rumah?"
        return templates.get(
            intent.next_action or "",
            "Maaf Kak, saya belum menangkap kebutuhan detailnya. Boleh jelaskan ingin pasang internet, cek paket, harga, coverage, atau jadwal teknisi?",
        )

    def _slot_prompt(
        self,
        intent: IntentMatch,
        missing_slots: list[str],
        context: str,
    ) -> str:
        labels = {
            "address": "alamat lengkap",
            "customer_name": "nama pelanggan",
            "phone_number": "nomor HP aktif",
            "package_name": "paket yang dipilih",
            "schedule_date": "tanggal pemasangan",
            "schedule_time": "jam pemasangan",
        }
        requested = ", ".join(labels.get(slot, slot) for slot in missing_slots)
        opener = {
            "ask_installation": "Bisa Kak, kami bantu proses pemasangan internet rumah.",
            "ask_coverage": "Siap Kak, saya bantu cek coverage jaringan.",
            "ask_installation_schedule": "Siap Kak, saya bantu cek jadwal teknisi.",
            "confirm_order": "Baik Kak, saya bantu siapkan order pemasangan.",
        }.get(intent.intent_code, "Siap Kak, saya bantu proses.")
        return f"{opener}{context} Mohon kirim {requested}."

    def _entity_context(self, entities: list[EntityMatch]) -> str:
        if not entities:
            return ""
        values = [
            entity.value
            for entity in entities
            if entity.entity_code in {"speed", "payment_method", "schedule_date", "schedule_time"}
        ]
        return f" (terdeteksi: {', '.join(values[:3])})" if values else ""

    def _decode_mapping(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "description": item.get("description"),
            "required_slots": self._decode_json_list(item.get("required_slots")),
            "optional_slots": self._decode_json_list(item.get("optional_slots")),
            "next_action": item.get("next_action"),
        }

    def _decode_json_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if not value:
            return []
        try:
            decoded = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(decoded, list):
            return []
        return [str(item) for item in decoded]

    def _unknown_intent(self) -> IntentMatch:
        return IntentMatch(
            intent_code="unknown",
            intent_name=self.intent_names.get("unknown", "Tidak diketahui"),
            score=0,
            confidence=0.0,
            matched_keywords=[],
            next_action=None,
            required_slots=[],
            optional_slots=[],
        )
