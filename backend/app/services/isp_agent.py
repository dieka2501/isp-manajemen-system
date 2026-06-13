from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Any


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


STOPWORDS = {
    "id": {
        "ada",
        "aku",
        "apakah",
        "bisa",
        "boleh",
        "dan",
        "di",
        "dong",
        "dulu",
        "ini",
        "itu",
        "kak",
        "kang",
        "ke",
        "min",
        "mohon",
        "saya",
        "sih",
        "tolong",
        "untuk",
        "ya",
        "yang",
    },
    "su": {
        "abdi",
        "aya",
        "bisa",
        "di",
        "ieu",
        "kang",
        "kanggo",
        "muhun",
        "pun",
        "punten",
        "teu",
        "tiasa",
        "wae",
    },
    "en": {
        "a",
        "an",
        "and",
        "any",
        "at",
        "can",
        "do",
        "for",
        "have",
        "hi",
        "i",
        "is",
        "it",
        "me",
        "my",
        "please",
        "the",
        "to",
        "what",
        "you",
        "your",
    },
}


def token_variants(token: str) -> set[str]:
    variants = {token}
    suffixes = ("nya", "na", "kah", "lah")
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            variants.add(token[: -len(suffix)])
    return variants


@dataclass(frozen=True)
class CatalogPhrase:
    intent_code: str
    lang_code: str
    raw_text: str
    normalized_text: str
    tokens: list[str]
    token_set: set[str]
    significant_tokens: set[str]
    weight: int
    source: str


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
    memory_update: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "intent": self.intent.as_dict(),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "entities": [entity.as_dict() for entity in self.entities],
            "missing_slots": self.missing_slots,
            "reply_text": self.reply_text,
            "memory_update": self.memory_update,
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
        self.sample_utterances = catalog.get("sample_utterances", [])
        self.internet_packages = catalog.get("internet_packages", [])
        self.coverage_areas = catalog.get("coverage_areas", [])
        self.payment_methods = catalog.get("payment_methods", [])
        self.intent_mappings = {
            item["intent_code"]: self._decode_mapping(item)
            for item in catalog.get("intent_mappings", [])
        }
        self.prepared_keywords = self._prepare_catalog_phrases(
            self.intent_keywords,
            text_keys=("normalized_keyword", "keyword"),
            source="keyword",
        )
        self.prepared_samples = self._prepare_catalog_phrases(
            self.sample_utterances,
            text_keys=("utterance",),
            source="sample",
            default_weight=3,
        )

    def answer(
        self,
        message_text: str,
        conversation_state: dict[str, Any] | None = None,
    ) -> AgentResponse:
        normalized_by_lang = self._normalize_by_language(message_text)
        language = self._detect_language(normalized_by_lang)
        normalized_message = normalized_by_lang[language]
        state = conversation_state or {}
        prior_slots = self._decode_slot_state(state.get("collected_slots"))
        waiting_for = self._decode_waiting_for(state.get("waiting_for"))
        entities = self._extract_entities(message_text, normalized_message, language)

        if waiting_for:
            memory_slots = self._extract_memory_slots(
                message_text=message_text,
                normalized_message=normalized_message,
                waiting_for=waiting_for,
                prior_slots=prior_slots,
                entities=entities,
            )
            if memory_slots:
                merged_slots = {**prior_slots, **memory_slots}
                for slot_name, slot_value in memory_slots.items():
                    entities.append(
                        EntityMatch(
                            entity_code=slot_name,
                            entity_name=self._slot_label(slot_name),
                            value=slot_value,
                            normalized_value=normalize_text(slot_value),
                            source="memory",
                        )
                    )
                remaining_slots = [
                    slot for slot in waiting_for if not str(merged_slots.get(slot) or "").strip()
                ]
                current_intent = str(state.get("current_intent") or "unknown")
                intent = IntentMatch(
                    intent_code=current_intent,
                    intent_name=self.intent_names.get(current_intent, current_intent),
                    score=12,
                    confidence=0.9,
                    matched_keywords=[f"memory:{slot}" for slot in memory_slots],
                    next_action=str(state.get("next_action") or "") or None,
                    required_slots=waiting_for,
                    optional_slots=[],
                )
                reply_text = self._compose_memory_reply(
                    current_intent=current_intent,
                    filled_slots=memory_slots,
                    remaining_slots=remaining_slots,
                    collected_slots=merged_slots,
                )
                memory_update = self._build_memory_update(
                    intent=intent,
                    entities=entities,
                    missing_slots=remaining_slots,
                    collected_slots=merged_slots,
                    reply_text=reply_text,
                )
                return AgentResponse(
                    language=language,
                    intent=intent,
                    candidates=[intent],
                    entities=entities,
                    missing_slots=remaining_slots,
                    reply_text=reply_text,
                    memory_update=memory_update,
                )

        candidates = self._rank_intents(normalized_message, language)
        intent = candidates[0] if candidates else self._unknown_intent()
        if intent.intent_code == "unknown" and state.get("current_topic"):
            reply_text = self._contextual_fallback_reply(state)
            return AgentResponse(
                language=language,
                intent=intent,
                candidates=candidates[:5],
                entities=entities,
                missing_slots=[],
                reply_text=reply_text,
                memory_update=self._contextual_memory_update(state, reply_text),
            )
        missing_slots = self._soft_missing_slots(
            intent,
            self._missing_slots(intent.required_slots, entities),
            entities,
        )
        reply_text = self._compose_reply(intent, entities, missing_slots)
        memory_update = self._build_memory_update(
            intent=intent,
            entities=entities,
            missing_slots=missing_slots,
            collected_slots=prior_slots,
            reply_text=reply_text,
        )

        return AgentResponse(
            language=language,
            intent=intent,
            candidates=candidates[:5],
            entities=entities,
            missing_slots=missing_slots,
            reply_text=reply_text,
            memory_update=memory_update,
        )

    def _normalize_by_language(self, message_text: str) -> dict[str, str]:
        base = normalize_text(message_text)
        languages = {
            str(rule["lang_code"])
            for rule in self.normalization_rules
            if rule.get("lang_code")
        } or {"id"}
        normalized = {lang_code: base for lang_code in languages}
        for lang_code in list(normalized):
            normalized[lang_code] = self._normalize_for_language(base, lang_code)
        return normalized

    def _normalize_for_language(self, value: str, language: str) -> str:
        normalized = normalize_text(value)
        rules = [
            rule
            for rule in self.normalization_rules
            if str(rule["lang_code"]) == language
        ]
        rules.sort(
            key=lambda item: len(normalize_text(str(item["source_text"])).split()),
            reverse=True,
        )
        for rule in rules:
            source = normalize_text(str(rule["source_text"]))
            replacement = normalize_text(str(rule["normalized_text"]))
            if not source or not replacement:
                continue
            normalized = re.sub(
                rf"\b{re.escape(source)}\b",
                replacement,
                normalized,
            )
        return normalized

    def _detect_language(self, normalized_by_lang: dict[str, str]) -> str:
        scores = {lang_code: 0 for lang_code in normalized_by_lang}
        language_cues = {
            "id": {"aku", "kak", "mau", "berapa", "berapaan", "dong", "saya"},
            "su": {"abdi", "aya", "hoyong", "kang", "naon", "punten", "rek", "sabaraha", "teu", "tos", "wae"},
            "en": {"can", "do", "hello", "hi", "how", "please", "what"},
        }

        for lang_code, normalized_message in normalized_by_lang.items():
            message_tokens = self._expanded_token_set(normalized_message.split())
            scores[lang_code] += len(message_tokens & language_cues.get(lang_code, set())) * 3

            for phrase in self.prepared_keywords:
                if phrase.lang_code != lang_code:
                    continue
                if self._contains_token_sequence(normalized_message, phrase.tokens):
                    scores[lang_code] += phrase.weight * 2
                    continue
                overlap = len(phrase.significant_tokens & message_tokens)
                if overlap >= 2:
                    scores[lang_code] += phrase.weight

        best_lang, best_score = max(
            scores.items(),
            key=lambda item: (item[1], 1 if item[0] == "id" else 0),
        )
        return best_lang if best_score > 0 else "id"

    def _rank_intents(self, normalized_message: str, language: str) -> list[IntentMatch]:
        scored: dict[str, dict[str, Any]] = {}
        message_tokens = self._expanded_token_set(normalized_message.split())
        significant_message_tokens = self._significant_tokens(message_tokens, language)

        for phrase in self.prepared_keywords:
            if phrase.lang_code != language:
                continue
            score = self._keyword_score(
                phrase=phrase,
                normalized_message=normalized_message,
                message_tokens=message_tokens,
                significant_message_tokens=significant_message_tokens,
            )
            if score <= 0:
                continue
            self._add_intent_score(
                scored=scored,
                intent_code=phrase.intent_code,
                score=score,
                matched_text=phrase.raw_text,
            )

        for phrase in self.prepared_samples:
            if phrase.lang_code != language:
                continue
            score = self._sample_score(
                phrase=phrase,
                normalized_message=normalized_message,
                significant_message_tokens=significant_message_tokens,
            )
            if score <= 0:
                continue
            self._add_intent_score(
                scored=scored,
                intent_code=phrase.intent_code,
                score=score,
                matched_text=f"sample: {phrase.raw_text}",
            )

        for intent_code, score, marker in self._heuristic_intent_scores(
            normalized_message,
            message_tokens,
        ):
            self._add_intent_score(
                scored=scored,
                intent_code=intent_code,
                score=score,
                matched_text=marker,
            )

        candidates: list[IntentMatch] = []
        for intent_code, item in scored.items():
            mapping = self.intent_mappings.get(intent_code, {})
            score = int(item["score"])
            if score < 3:
                continue
            candidates.append(
                IntentMatch(
                    intent_code=intent_code,
                    intent_name=self.intent_names.get(intent_code, intent_code),
                    score=score,
                    confidence=round(min(0.99, score / 18), 2),
                    matched_keywords=list(dict.fromkeys(item["keywords"])),
                    next_action=mapping.get("next_action"),
                    required_slots=mapping.get("required_slots", []),
                    optional_slots=mapping.get("optional_slots", []),
                )
            )

        candidates.sort(key=lambda item: (item.score, item.confidence), reverse=True)
        return candidates or [self._unknown_intent()]

    def _prepare_catalog_phrases(
        self,
        rows: list[dict[str, Any]],
        *,
        text_keys: tuple[str, ...],
        source: str,
        default_weight: int = 1,
    ) -> list[CatalogPhrase]:
        phrases: list[CatalogPhrase] = []
        for row in rows:
            lang_code = str(row.get("lang_code") or "id")
            raw_text = ""
            for key in text_keys:
                raw_text = str(row.get(key) or "").strip()
                if raw_text:
                    break
            normalized_text = self._normalize_for_language(raw_text, lang_code)
            if not normalized_text:
                continue
            tokens = normalized_text.split()
            token_set = self._expanded_token_set(tokens)
            phrases.append(
                CatalogPhrase(
                    intent_code=str(row["intent_code"]),
                    lang_code=lang_code,
                    raw_text=raw_text,
                    normalized_text=normalized_text,
                    tokens=tokens,
                    token_set=token_set,
                    significant_tokens=self._significant_tokens(token_set, lang_code),
                    weight=int(row.get("weight") or default_weight),
                    source=source,
                )
            )
        return phrases

    def _expanded_token_set(self, tokens: list[str]) -> set[str]:
        expanded: set[str] = set()
        for token in tokens:
            expanded.update(token_variants(token))
        return expanded

    def _significant_tokens(self, tokens: set[str], language: str) -> set[str]:
        stopwords = STOPWORDS.get(language, set()) | STOPWORDS["id"]
        return {token for token in tokens if len(token) > 1 and token not in stopwords}

    def _keyword_score(
        self,
        *,
        phrase: CatalogPhrase,
        normalized_message: str,
        message_tokens: set[str],
        significant_message_tokens: set[str],
    ) -> int:
        if self._contains_token_sequence(normalized_message, phrase.tokens):
            return phrase.weight * max(2, len(phrase.tokens) * 2)

        phrase_tokens = phrase.significant_tokens or phrase.token_set
        overlap = len(phrase_tokens & significant_message_tokens)
        if overlap == 0:
            return 0

        coverage = overlap / len(phrase_tokens)
        if coverage == 1:
            multiplier = 1.5 if len(phrase_tokens) > 1 else 0.9
        elif overlap >= 2 and coverage >= 0.5:
            multiplier = 0.75 + coverage
        else:
            multiplier = 0.0

        return round(phrase.weight * multiplier)

    def _sample_score(
        self,
        *,
        phrase: CatalogPhrase,
        normalized_message: str,
        significant_message_tokens: set[str],
    ) -> int:
        if not phrase.significant_tokens:
            return 0

        overlap = len(phrase.significant_tokens & significant_message_tokens)
        ratio = SequenceMatcher(None, normalized_message, phrase.normalized_text).ratio()
        if overlap < 2 and ratio < 0.78:
            return 0

        union_size = len(phrase.significant_tokens | significant_message_tokens) or 1
        jaccard = overlap / union_size
        sample_coverage = overlap / len(phrase.significant_tokens)
        message_coverage = overlap / (len(significant_message_tokens) or 1)
        similarity = (jaccard * 0.45) + (sample_coverage * 0.3) + (message_coverage * 0.15) + (ratio * 0.1)
        if similarity < 0.28:
            return 0
        return max(3, round(phrase.weight * 4 * similarity))

    def _contains_token_sequence(self, normalized_message: str, phrase_tokens: list[str]) -> bool:
        if not phrase_tokens:
            return False
        phrase = " ".join(phrase_tokens)
        return re.search(rf"\b{re.escape(phrase)}\b", normalized_message) is not None

    def _add_intent_score(
        self,
        *,
        scored: dict[str, dict[str, Any]],
        intent_code: str,
        score: int,
        matched_text: str,
    ) -> None:
        bucket = scored.setdefault(intent_code, {"score": 0, "keywords": []})
        bucket["score"] += score
        bucket["keywords"].append(matched_text)

    def _heuristic_intent_scores(
        self,
        normalized_message: str,
        message_tokens: set[str],
    ) -> list[tuple[str, int, str]]:
        scores: list[tuple[str, int, str]] = []

        def has_any(words: set[str]) -> bool:
            return bool(message_tokens & words)

        def has_phrase(pattern: str) -> bool:
            return re.search(pattern, normalized_message) is not None

        if has_any({"halo", "hai", "hi", "pagi", "siang", "sore", "malam"}):
            scores.append(("greeting", 4, "heuristic:greeting"))
        if has_any({"makasih", "terima", "thanks", "thank"}):
            scores.append(("thanks", 4, "heuristic:thanks"))

        if has_any({"coverage", "cover", "tercover", "jaringan", "wilayah", "daerah", "area", "lokasi"}) or has_phrase(r"\bmasuk jaringan\b"):
            scores.append(("ask_coverage", 5, "heuristic:coverage"))
        if has_any({"harga", "biaya", "tarif", "sabulan", "sebulan", "bulanan", "promo"}) or has_phrase(r"\bberapa\b"):
            scores.append(("ask_price", 5, "heuristic:price"))
        if has_any({"bayar", "pembayaran", "transfer", "qris", "cash", "tagihan", "ewallet", "wallet"}):
            scores.append(("ask_payment_method", 5, "heuristic:payment"))
        if has_any({"jadwal", "teknisi", "kapan", "besok", "datang", "sumping", "iraha"}) or has_phrase(r"\bhari ini\b"):
            scores.append(("ask_installation_schedule", 5, "heuristic:schedule"))
        if has_any({"paket", "speed", "mbps", "mega", "unlimited"}) and has_any({"apa", "daftar", "pilihan", "info", "lihat", "murah"}):
            scores.append(("ask_package", 5, "heuristic:package"))
        if has_any({"paket"}) and has_any({"harga", "biaya", "tarif", "info", "tahu"}) and not has_phrase(r"\b\d+\s*(?:mbps|mega|gbps)?\b"):
            scores.append(("ask_package", 16, "heuristic:package_price_overview"))
        if has_any({"pasang", "daftar", "langganan", "berlangganan", "install", "pemasangan", "masang"}) and not has_any({"jaringan", "coverage", "jadwal", "teknisi"}):
            scores.append(("ask_installation", 4, "heuristic:installation"))
        if has_phrase(r"\b(?:gak|nggak|ga|tidak|teu)?\s*jadi\b") or has_any({"batal", "cancel"}):
            scores.append(("cancel_order", 8, "heuristic:cancel"))

        return scores

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
            ("speed", "Kecepatan internet", r"\b\d+\s*(?:mb|mbps|mega|gbps)\b"),
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
        payment_aliases = {
            "qris": "QRIS",
            "transfer": "transfer bank",
            "cash": "cash",
            "tunai": "cash",
            "ewallet": "e-wallet",
            "e wallet": "e-wallet",
            "wallet": "e-wallet",
        }
        for marker, value in payment_aliases.items():
            if re.search(rf"\b{re.escape(marker)}\b", normalized_message):
                key = ("payment_method", normalize_text(value))
                if key not in seen:
                    seen.add(key)
                    entities.append(
                        EntityMatch(
                            entity_code="payment_method",
                            entity_name="Metode pembayaran",
                            value=value,
                            normalized_value=normalize_text(value),
                            source="heuristic",
                        )
                    )
                break
        return entities

    def _missing_slots(self, required_slots: list[str], entities: list[EntityMatch]) -> list[str]:
        entity_codes = {entity.entity_code for entity in entities}
        return [slot for slot in required_slots if slot not in entity_codes]

    def _decode_waiting_for(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return []
            if isinstance(decoded, list):
                return [str(item) for item in decoded if str(item).strip()]
        return []

    def _decode_slot_state(self, value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            return {
                str(key): str(slot_value)
                for key, slot_value in value.items()
                if str(slot_value).strip()
            }
        if isinstance(value, str) and value.strip():
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(decoded, dict):
                return {
                    str(key): str(slot_value)
                    for key, slot_value in decoded.items()
                    if str(slot_value).strip()
                }
        return {}

    def _extract_memory_slots(
        self,
        *,
        message_text: str,
        normalized_message: str,
        waiting_for: list[str],
        prior_slots: dict[str, str],
        entities: list[EntityMatch],
    ) -> dict[str, str]:
        filled: dict[str, str] = {}
        filled.update(
            {
                entity.entity_code: entity.value
                for entity in entities
                if entity.entity_code in waiting_for and entity.value.strip()
            }
        )

        if "phone_number" in waiting_for and "phone_number" not in filled:
            match = re.search(r"(?:\+?62|0)?8\d{7,12}", message_text)
            if match:
                filled["phone_number"] = match.group(0)

        parts = [part.strip() for part in re.split(r"[,;\n]+", message_text) if part.strip()]
        if (
            "customer_name" in waiting_for
            and "customer_name" not in filled
            and parts
            and (len(parts) > 1 or "address" not in waiting_for)
        ):
            name_candidate = parts[0]
            if not re.search(r"\d", name_candidate) and 2 <= len(name_candidate) <= 60:
                filled["customer_name"] = name_candidate

        if "usage_need" in waiting_for and "usage_need" not in filled:
            usage_markers = {
                "keluarga": "keluarga",
                "rumah": "rumahan",
                "gaming": "gaming",
                "game": "gaming",
                "kerja": "kerja dari rumah",
                "wfh": "kerja dari rumah",
                "sekolah": "sekolah",
                "streaming": "streaming",
                "ringan": "pemakaian ringan",
            }
            for marker, label in usage_markers.items():
                if re.search(rf"\b{re.escape(marker)}\b", normalized_message):
                    filled["usage_need"] = label
                    break

        address_slots = [slot for slot in ("address", "area") if slot in waiting_for]
        if address_slots and not any(slot in filled for slot in address_slots):
            address_value = self._infer_address_from_followup(
                message_text,
                normalized_message,
                parts,
            )
            if address_value:
                filled["address" if "address" in waiting_for else "area"] = address_value

        if "package_name" in waiting_for and "package_name" not in filled:
            if re.search(r"\b\d+\s*(?:mbps|mega|gbps)\b", message_text.lower()):
                filled["package_name"] = message_text.strip()

        return {
            slot: value
            for slot, value in filled.items()
            if slot in waiting_for and str(value).strip() and not prior_slots.get(slot)
        }

    def _infer_address_from_followup(
        self,
        message_text: str,
        normalized_message: str,
        parts: list[str],
    ) -> str | None:
        if any(marker in normalized_message for marker in ("jalan", "jl", "alamat", "komplek", "blok")):
            return message_text.strip()
        if len(parts) >= 2:
            last_part = parts[-1]
            if not re.search(r"\d", last_part) and len(last_part) >= 3:
                return last_part
        if len(normalized_message.split()) <= 5 and not self._looks_like_question(normalized_message):
            return message_text.strip()
        return None

    def _looks_like_question(self, normalized_message: str) -> bool:
        markers = (
            "apa",
            "berapa",
            "bisa",
            "gimana",
            "harga",
            "paket",
            "promo",
            "qris",
            "transfer",
        )
        return any(re.search(rf"\b{marker}\b", normalized_message) for marker in markers)

    def _build_memory_update(
        self,
        *,
        intent: IntentMatch,
        entities: list[EntityMatch],
        missing_slots: list[str],
        collected_slots: dict[str, str],
        reply_text: str,
    ) -> dict[str, Any] | None:
        if intent.intent_code == "unknown":
            return None

        slots = dict(collected_slots)
        for entity in entities:
            if entity.entity_code in {
                "address",
                "area",
                "customer_name",
                "phone_number",
                "package_name",
                "speed",
                "usage_need",
            }:
                slots.setdefault(entity.entity_code, entity.value)

        waiting_for = list(missing_slots)
        if intent.next_action == "show_package_list":
            waiting_for = [slot for slot in waiting_for if slot != "usage_need"]
            if not slots.get("usage_need"):
                waiting_for.append("usage_need")
        if intent.intent_code == "choose_package":
            for slot in ("customer_name", "phone_number", "address", "schedule_date"):
                if not slots.get(slot) and slot not in waiting_for:
                    waiting_for.append(slot)

        stage = "collecting_slots" if waiting_for else "ready"
        return {
            "current_intent": intent.intent_code,
            "current_topic": self._topic_for_intent(intent.intent_code),
            "stage": stage,
            "waiting_for": waiting_for,
            "collected_slots": slots,
            "last_bot_question": reply_text,
            "next_action": intent.next_action,
        }

    def _contextual_memory_update(
        self,
        state: dict[str, Any],
        reply_text: str,
    ) -> dict[str, Any]:
        return {
            "current_intent": state.get("current_intent") or "unknown",
            "current_topic": state.get("current_topic"),
            "stage": state.get("stage") or "ready",
            "waiting_for": self._decode_waiting_for(state.get("waiting_for")),
            "collected_slots": self._decode_slot_state(state.get("collected_slots")),
            "last_bot_question": reply_text,
            "next_action": state.get("next_action"),
        }

    def _compose_memory_reply(
        self,
        *,
        current_intent: str,
        filled_slots: dict[str, str],
        remaining_slots: list[str],
        collected_slots: dict[str, str],
    ) -> str:
        acknowledgements = []
        if "customer_name" in filled_slots:
            acknowledgements.append(f"nama {filled_slots['customer_name']}")
        if "phone_number" in filled_slots:
            acknowledgements.append(f"nomor {filled_slots['phone_number']}")
        if "address" in filled_slots:
            acknowledgements.append(f"alamat {filled_slots['address']}")
        if "area" in filled_slots:
            acknowledgements.append(f"area {filled_slots['area']}")
        if "usage_need" in filled_slots:
            acknowledgements.append(f"kebutuhan {filled_slots['usage_need']}")

        opener = "Siap Kak"
        if acknowledgements:
            opener = f"Siap Kak, {' dan '.join(acknowledgements[:3])} saya catat."

        if not remaining_slots:
            if current_intent == "ask_coverage" and (
                filled_slots.get("address") or filled_slots.get("area")
            ):
                return self._coverage_reply(filled_slots.get("area") or filled_slots.get("address"))
            if current_intent in {"ask_installation", "confirm_order", "choose_package"}:
                if current_intent == "confirm_order":
                    return f"{opener} Datanya sudah cukup untuk kami bantu proses pengecekan coverage dan pemasangan."
                return (
                    f"{opener} Kita bisa lanjut pelan-pelan. "
                    "Kalau Kakak masih mau tanya paket, harga, atau coverage dulu, silakan."
                )
            if current_intent == "ask_package" and collected_slots.get("usage_need"):
                return (
                    f"{opener} Untuk kebutuhan {collected_slots['usage_need']}, "
                    "nanti bisa kami arahkan ke paket rumahan yang stabil. Boleh lanjut kirim area pemasangannya?"
                )
            return f"{opener} Ada detail lain yang ingin Kakak tambahkan?"

        requested = self._format_slot_request(remaining_slots)
        return f"{opener} Mohon kirim {requested} agar prosesnya bisa dilanjutkan."

    def _format_slot_request(self, slots: list[str]) -> str:
        return ", ".join(self._slot_label(slot) for slot in slots)

    def _slot_label(self, slot: str) -> str:
        return {
            "address": "alamat lengkap",
            "area": "area pemasangan",
            "customer_name": "nama pelanggan",
            "phone_number": "nomor HP aktif",
            "package_name": "paket yang dipilih",
            "schedule_date": "tanggal pemasangan",
            "schedule_time": "jam pemasangan",
            "usage_need": "kebutuhan pemakaian",
            "speed": "speed yang diminati",
        }.get(slot, slot)

    def _compose_reply(
        self,
        intent: IntentMatch,
        entities: list[EntityMatch],
        missing_slots: list[str],
    ) -> str:
        context = self._entity_context(entities)
        missing_slots = self._soft_missing_slots(intent, missing_slots, entities)
        if missing_slots:
            return self._slot_prompt(intent, missing_slots, context)

        templates = {
            "show_package_list": self._package_overview_reply(entities),
            "show_price": self._price_overview_reply(entities, context),
            "ask_or_validate_address": self._coverage_reply(self._area_context(entities)),
            "check_technician_schedule": (
                "Bisa kami bantu jadwalkan teknisi. Mohon kirim alamat lengkap, paket yang dipilih, "
                "dan preferensi waktu pemasangan."
            ),
            "show_payment_methods": self._payment_methods_reply(entities),
            "create_order": (
                "Baik Kak, data utama sudah cukup untuk diproses. Saya teruskan sebagai permintaan pemasangan."
            ),
            "ask_address_or_show_packages": (
                "Bisa Kak. Kita bisa mulai dari lihat gambaran paket dulu atau cek area pemasangan. "
                "Kakak ingin tanya paket/harga dulu, atau sebutkan area pemasangannya?"
            ),
            "ask_speed": (
                f"Siap Kak, saya bantu info pilihan speed{context}. "
                "Boleh ceritakan kebutuhan pemakaiannya untuk berapa orang atau perangkat?"
            ),
            "ask_requirement": (
                "Syarat pemasangan biasanya membutuhkan nama pelanggan, nomor HP aktif, alamat lengkap, "
                "dan paket yang dipilih. Nanti tim akan validasi coverage terlebih dahulu."
            ),
            "ask_installation_fee": (
                self._installation_fee_reply(entities)
            ),
            "ask_promo": (
                "Siap Kak, saya bantu cek promo yang tersedia. Boleh info area pemasangan dan speed/paket "
                "yang diminati?"
            ),
            "ask_contract": (
                "Untuk masa kontrak dan ketentuan berhenti langganan, saya bantu arahkan sesuai paket "
                "yang dipilih. Boleh sebutkan paket atau speed yang diminati?"
            ),
            "ask_router": (
                "Untuk modem/router, detail perangkat mengikuti paket dan kebijakan client. "
                "Boleh info paket atau speed yang diminati agar saya bantu cekkan?"
            ),
            "ask_availability_today": (
                "Saya bantu cek kemungkinan pemasangan cepat ya Kak. Untuk awal, sebutkan area pemasangan "
                "dan paket/speed yang diminati dulu."
            ),
            "compare_package": (
                self._package_overview_reply(entities)
            ),
            "choose_package": (
                f"Siap Kak, saya catat pilihan {self._selected_package_label(entities)}{context}. "
                "Untuk lanjut pemasangan, boleh kirim nama, nomor HP aktif, alamat lengkap, dan jadwal yang diinginkan?"
            ),
            "provide_address": (
                "Terima kasih Kak, alamatnya saya terima. Saya bantu teruskan untuk cek coverage jaringan."
            ),
            "provide_contact": (
                "Terima kasih Kak, kontaknya saya catat. Kalau Kakak masih ingin tanya paket atau harga dulu, "
                "silakan; kalau mau lanjut, cukup kirim area/alamat pemasangannya."
            ),
            "cancel_order": (
                "Tidak apa-apa Kak. Saya tidak lanjutkan dulu. Kalau nanti mau tanya paket, harga, atau coverage lagi, "
                "saya siap bantu."
            ),
            "complaint_installation": (
                "Mohon maaf atas kendalanya Kak. Boleh kirim nomor HP terdaftar, alamat pemasangan, "
                "dan kendala yang terjadi agar tim bisa bantu follow up."
            ),
            "follow_up_installation": (
                "Siap Kak, saya bantu follow up status teknisi. Mohon kirim nomor HP terdaftar "
                "atau alamat pemasangan."
            ),
            "negotiate_price": (
                "Saya bantu cek opsi yang paling sesuai ya Kak. Boleh sebutkan budget, area pemasangan, "
                "dan kebutuhan speed-nya?"
            ),
            "ask_after_sales": (
                "Untuk bantuan setelah pemasangan, boleh jelaskan kendalanya dan kirim nomor HP terdaftar "
                "agar tim support bisa cek datanya."
            ),
        }
        if intent.intent_code in ("greeting", "thanks"):
            return "Halo Kak, terima kasih sudah menghubungi kami. Ada yang bisa saya bantu terkait internet rumah?"
        template_key = intent.next_action or intent.intent_code
        return templates.get(
            template_key,
            "Maaf Kak, saya belum nyambung. Kakak boleh tanya paket, harga, coverage, atau cara pemasangan; saya ikuti dulu pertanyaannya.",
        )

    def _contextual_fallback_reply(self, state: dict[str, Any]) -> str:
        topic = str(state.get("current_topic") or "")
        if topic == "package_info":
            return (
                "Betul Kak, tadi kita sedang bahas paket dan harga. "
                "Mau saya ringkas lagi per paket, atau Kakak ingin cek paket yang cocok untuk area tertentu?"
            )
        if topic == "coverage_check":
            return (
                "Iya Kak, konteksnya masih cek coverage. "
                "Kakak bisa sebutkan kecamatan/kelurahan atau patokan terdekat supaya saya cekkan."
            )
        if topic == "payment":
            return (
                "Masih soal pembayaran ya Kak. "
                "Kalau mau, sebutkan metodenya seperti QRIS, transfer, cash, atau e-wallet."
            )
        if topic == "order_confirmation":
            return (
                "Siap Kak, konteksnya masih proses pemasangan. "
                "Kakak bisa lanjut kirim data yang belum ada, atau tanya paket/coverage dulu juga boleh."
            )
        return (
            "Saya ikuti dulu konteks sebelumnya ya Kak. "
            "Boleh tulis ulang bagian yang ingin dicek: paket, harga, coverage, pembayaran, atau pemasangan?"
        )

    def _topic_for_intent(self, intent_code: str) -> str:
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

    def _package_overview_reply(self, entities: list[EntityMatch]) -> str:
        package_summary = self._format_package_summary(entities)
        if not package_summary:
            return (
                "Bisa Kak. Paket internet biasanya disesuaikan dari kebutuhan: pemakaian ringan, keluarga, "
                "kerja dari rumah, streaming, atau gaming. Kakak mau lihat rekomendasi berdasarkan kebutuhan, "
                "atau sebutkan area dulu supaya infonya lebih pas?"
            )
        return (
            f"Bisa Kak. {package_summary}\n\n"
            "Kalau Kakak mau, sebutkan kebutuhan pemakaian atau area pemasangannya supaya saya bantu pilihkan yang paling pas."
        )

    def _payment_methods_reply(self, entities: list[EntityMatch]) -> str:
        method = self._payment_method_context(entities)
        if method:
            matched = self._find_payment_method(method)
            if matched and int(matched.get("is_available", 0) or 0) == 1:
                return f"Bisa Kak, pembayaran lewat {matched['method_name']} tersedia ya."
            return f"Untuk {method}, saya belum punya data ketersediaan pastinya Kak. Saya bantu cekkan dulu ya."

        available = [
            item["method_name"]
            for item in self.payment_methods
            if int(item.get("is_available", 0) or 0) == 1
        ]
        if not available:
            return "Metode pembayaran belum tersedia di data kami Kak. Saya bantu cekkan dulu ya."
        return f"Bisa Kak, pembayaran tersedia lewat {', '.join(available)}."

    def _coverage_reply(self, area: str | None) -> str:
        if not area:
            return (
                "Bisa Kak, saya bantu cek coverage. Untuk awal, sebutkan area/kecamatan dulu juga cukup; "
                "alamat lengkap bisa nanti kalau mau dilanjutkan."
            )
        coverage = self._find_coverage_area(area)
        if coverage and coverage.get("coverage_status") == "covered":
            speed_range = self._package_speed_range()
            suffix = f" Paket yang tersedia mulai dari {speed_range}." if speed_range else ""
            return f"Untuk area {area} sudah tercover Kak.{suffix}"
        if coverage and coverage.get("coverage_status") == "partial":
            return f"Area {area} sebagian sudah tercover Kak. Boleh kirim patokan/alamat singkat supaya saya cek lebih tepat?"
        if coverage and coverage.get("coverage_status") == "not_covered":
            return f"Untuk area {area}, data kami menunjukkan belum tercover Kak."
        return f"Untuk area {area}, saya belum punya data coverage pasti. Boleh kirim kecamatan/kelurahan atau patokan terdekat?"

    def _price_overview_reply(self, entities: list[EntityMatch], context: str) -> str:
        package_summary = self._format_package_summary(entities)
        if not package_summary:
            return (
                f"Bisa Kak, saya bantu arahkan info harga paket{context}. "
                "Harga bisa berbeda tergantung speed dan area, jadi Kakak bisa sebutkan speed yang diminati "
                "atau area pemasangannya dulu."
            )
        return (
            f"Bisa Kak, ini gambaran harga paket{context}:\n{package_summary}\n\n"
            "Harga final tetap bisa dikonfirmasi lagi sesuai area coverage. Kakak boleh sebutkan area atau speed yang diminati."
        )

    def _installation_fee_reply(self, entities: list[EntityMatch]) -> str:
        packages = self._matching_packages(entities)
        if not packages:
            return (
                "Siap Kak, biaya pemasangan bisa berbeda sesuai paket dan kebijakan client. "
                "Boleh sebutkan area atau paket yang diminati dulu."
            )
        lines = []
        for package in packages:
            lines.append(
                f"- {package['package_name']} {package['speed_mbps']} Mbps: instalasi {self._installation_label(package)}"
            )
        return (
            "Siap Kak, ini biaya instalasi sementara:\n"
            + "\n".join(lines)
            + "\n\nKalau Kakak sebutkan area pemasangan, saya bisa bantu cocokan paket yang tersedia."
        )

    def _format_package_summary(self, entities: list[EntityMatch]) -> str:
        packages = self._matching_packages(entities)
        if not packages:
            return ""
        area = self._area_context(entities)
        intro = (
            f"Untuk area {area}, paket yang tersedia:"
            if area
            else "Sementara paket yang tersedia:"
        )
        lines = [intro]
        for index, package in enumerate(packages, start=1):
            benefits = ", ".join(str(item) for item in package.get("benefits") or [])
            benefit_text = f" Benefit: {benefits}." if benefits else ""
            lines.append(
                f"{index}. {package['package_name']} {package['speed_mbps']} Mbps - "
                f"{self._rupiah(package['monthly_price'])}/bulan, "
                f"instalasi {self._installation_label(package)}.{benefit_text}"
            )
        return "\n".join(lines)

    def _matching_packages(self, entities: list[EntityMatch]) -> list[dict[str, Any]]:
        packages = [
            package
            for package in self.internet_packages
            if int(package.get("is_active", 1) or 0) == 1
        ]
        speed = self._speed_context(entities)
        if speed:
            speed_matches = [
                package
                for package in packages
                if int(package.get("speed_mbps") or 0) == speed
            ]
            if speed_matches:
                packages = speed_matches

        area = self._area_context(entities)
        if not area:
            return packages

        normalized_area = normalize_text(area)
        matched = [
            package
            for package in packages
            if self._package_covers_area(package, normalized_area)
        ]
        return matched or packages

    def _selected_package_label(self, entities: list[EntityMatch]) -> str:
        speed = self._speed_context(entities)
        if speed:
            for package in self.internet_packages:
                if int(package.get("speed_mbps") or 0) == speed:
                    return f"{package['package_name']} {speed} Mbps"
            return f"paket {speed} Mbps"
        return "paketnya"

    def _package_covers_area(self, package: dict[str, Any], normalized_area: str) -> bool:
        for area in package.get("areas") or []:
            normalized_package_area = normalize_text(str(area))
            if normalized_package_area and (
                normalized_package_area in normalized_area
                or normalized_area in normalized_package_area
            ):
                return True
        return False

    def _area_context(self, entities: list[EntityMatch]) -> str | None:
        for entity in entities:
            if entity.entity_code in {"area", "address"} and entity.value.strip():
                return entity.value.strip()
        return None

    def _payment_method_context(self, entities: list[EntityMatch]) -> str | None:
        for entity in entities:
            if entity.entity_code == "payment_method" and entity.value.strip():
                return entity.value.strip()
        return None

    def _find_payment_method(self, value: str) -> dict[str, Any] | None:
        normalized = normalize_text(value)
        aliases = {
            "transfer": "bank_transfer",
            "transfer bank": "bank_transfer",
            "bank transfer": "bank_transfer",
            "qris": "qris",
            "cash": "cash",
            "tunai": "cash",
            "e wallet": "ewallet",
            "ewallet": "ewallet",
            "wallet": "ewallet",
        }
        code = aliases.get(normalized, normalized.replace(" ", "_"))
        for method in self.payment_methods:
            if method.get("method_code") == code or normalize_text(str(method.get("method_name"))) == normalized:
                return method
        return None

    def _find_coverage_area(self, value: str) -> dict[str, Any] | None:
        normalized = normalize_text(value)
        for area in self.coverage_areas:
            candidates = [
                area.get("area_name"),
                area.get("city"),
                area.get("district"),
                area.get("area_code"),
            ]
            for candidate in candidates:
                normalized_candidate = normalize_text(str(candidate or ""))
                if normalized_candidate and (
                    normalized_candidate in normalized or normalized in normalized_candidate
                ):
                    return area
        return None

    def _package_speed_range(self) -> str:
        speeds = sorted(
            {
                int(package.get("speed_mbps") or 0)
                for package in self.internet_packages
                if int(package.get("is_active", 1) or 0) == 1
            }
        )
        if not speeds:
            return ""
        if len(speeds) == 1:
            return f"{speeds[0]} Mbps"
        return f"{speeds[0]} Mbps sampai {speeds[-1]} Mbps"

    def _speed_context(self, entities: list[EntityMatch]) -> int | None:
        for entity in entities:
            if entity.entity_code != "speed":
                continue
            match = re.search(r"\d+", entity.value)
            if match:
                return int(match.group(0))
        return None

    def _installation_label(self, package: dict[str, Any]) -> str:
        label = str(package.get("installation_fee_label") or "").strip()
        if label:
            return label
        return self._rupiah(package.get("installation_fee") or 0)

    def _rupiah(self, value: Any) -> str:
        try:
            amount = int(value)
        except (TypeError, ValueError):
            amount = 0
        return f"Rp {amount:,}".replace(",", ".")

    def _soft_missing_slots(
        self,
        intent: IntentMatch,
        missing_slots: list[str],
        entities: list[EntityMatch],
    ) -> list[str]:
        if not missing_slots:
            return []
        entity_codes = {entity.entity_code for entity in entities}
        if intent.intent_code == "ask_installation":
            if "address" in missing_slots and "area" not in entity_codes:
                return ["address"]
            return []
        if intent.intent_code == "choose_package":
            if "address" in missing_slots and "area" not in entity_codes:
                return ["address"]
            return []
        return missing_slots

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
        if intent.intent_code == "ask_installation" and missing_slots == ["address"]:
            return (
                "Bisa Kak. Kita mulai pelan-pelan dulu. "
                "Kalau mau cek area, sebutkan kecamatan/kelurahan pemasangannya saja dulu; "
                "kalau masih mau tanya paket atau harga, silakan."
            )
        if intent.intent_code == "choose_package" and missing_slots == ["address"]:
            return (
                "Siap Kak. Sebelum masuk data pelanggan, kita cek area pemasangannya dulu ya. "
                "Cukup sebutkan kecamatan/kelurahan atau alamat singkatnya."
            )
        if intent.intent_code == "ask_coverage" and missing_slots == ["address"]:
            return (
                "Siap Kak, saya bantu cek coverage. Untuk awal, sebutkan area/kecamatan dulu juga cukup; "
                "alamat lengkap bisa nanti kalau mau dilanjutkan."
            )
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
