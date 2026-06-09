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
        self.sample_utterances = catalog.get("sample_utterances", [])
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
        if has_any({"pasang", "daftar", "langganan", "berlangganan", "install", "pemasangan", "masang"}) and not has_any({"jaringan", "coverage", "jadwal", "teknisi"}):
            scores.append(("ask_installation", 4, "heuristic:installation"))

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
            "ask_speed": (
                f"Siap Kak, saya bantu info pilihan speed{context}. "
                "Boleh ceritakan kebutuhan pemakaiannya untuk berapa orang atau perangkat?"
            ),
            "ask_requirement": (
                "Syarat pemasangan biasanya membutuhkan nama pelanggan, nomor HP aktif, alamat lengkap, "
                "dan paket yang dipilih. Nanti tim akan validasi coverage terlebih dahulu."
            ),
            "ask_installation_fee": (
                "Siap Kak, biaya pemasangan bisa berbeda sesuai paket dan kebijakan client. "
                "Boleh kirim area atau alamat lengkap agar kami cek info biaya awalnya?"
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
                "Saya bantu cek kemungkinan pemasangan cepat ya Kak. Mohon kirim alamat lengkap, "
                "paket yang diminati, dan nomor HP aktif."
            ),
            "compare_package": (
                "Siap Kak, saya bantu bandingkan paket. Boleh sebutkan prioritasnya: harga termurah, "
                "speed lebih tinggi, stabil untuk kerja, atau gaming?"
            ),
            "choose_package": (
                f"Siap Kak, pilihan paketnya saya catat{context}. "
                "Mohon kirim nama pelanggan, nomor HP aktif, dan alamat lengkap untuk validasi coverage."
            ),
            "provide_address": (
                "Terima kasih Kak, alamatnya saya terima. Saya bantu teruskan untuk cek coverage jaringan."
            ),
            "provide_contact": (
                "Terima kasih Kak, kontaknya saya catat. Mohon kirim alamat lengkap dan paket yang diminati "
                "agar proses pemasangan bisa dilanjutkan."
            ),
            "cancel_order": (
                "Baik Kak, saya catat permintaan pembatalan/penundaannya. Boleh info nomor HP terdaftar "
                "atau alamat pemasangan agar tim bisa cek datanya?"
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
