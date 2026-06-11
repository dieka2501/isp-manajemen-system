from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.isp_agent import ISPCSAgent


def build_catalog() -> dict[str, list[dict[str, Any]]]:
    intents = [
        ("ask_installation", "Tanya pemasangan"),
        ("ask_package", "Tanya paket internet"),
        ("ask_price", "Tanya harga"),
        ("ask_coverage", "Cek area jaringan"),
        ("ask_payment_method", "Tanya metode pembayaran"),
        ("choose_package", "Memilih paket"),
        ("follow_up_installation", "Follow-up pemasangan"),
        ("greeting", "Sapaan awal"),
        ("thanks", "Ucapan terima kasih"),
        ("unknown", "Tidak diketahui"),
    ]
    return {
        "intents": [
            {"intent_code": code, "intent_name": name, "description": None}
            for code, name in intents
        ],
        "intent_keywords": [
            {
                "intent_code": "ask_price",
                "intent_name": "Tanya harga",
                "lang_code": "id",
                "keyword": "berapa harganya?",
                "normalized_keyword": "harga",
                "formality_level": "informal",
                "weight": 5,
                "notes": None,
            },
            {
                "intent_code": "ask_payment_method",
                "intent_name": "Tanya metode pembayaran",
                "lang_code": "id",
                "keyword": "ada qris?",
                "normalized_keyword": "qris",
                "formality_level": "informal",
                "weight": 4,
                "notes": None,
            },
        ],
        "entity_keywords": [],
        "normalization_rules": [
            {"lang_code": "id", "source_text": "30mb", "normalized_text": "30 Mbps", "notes": None},
            {"lang_code": "id", "source_text": "berapaan", "normalized_text": "berapa", "notes": None},
            {"lang_code": "id", "source_text": "udah", "normalized_text": "sudah", "notes": None},
            {"lang_code": "su", "source_text": "sabaraha", "normalized_text": "berapa", "notes": None},
        ],
        "sample_utterances": [
            {
                "intent_code": "ask_installation",
                "lang_code": "id",
                "utterance": "Saya mau pasang internet, bisa?",
                "formality_level": "informal",
                "expected_entities": "{}",
                "notes": None,
            },
            {
                "intent_code": "ask_package",
                "lang_code": "su",
                "utterance": "Paketna aya naon wae kang?",
                "formality_level": "informal",
                "expected_entities": "{}",
                "notes": None,
            },
            {
                "intent_code": "follow_up_installation",
                "lang_code": "id",
                "utterance": "Teknisinya sudah sampai mana ya? Saya sudah menunggu dari pagi",
                "formality_level": "semi_formal",
                "expected_entities": "{}",
                "notes": None,
            },
            {
                "intent_code": "choose_package",
                "lang_code": "id",
                "utterance": "Saya ambil paket 50 Mbps saja",
                "formality_level": "semi_formal",
                "expected_entities": "{}",
                "notes": None,
            },
        ],
        "intent_mappings": [
            {
                "intent_code": "ask_installation",
                "description": "Customer wants installation",
                "required_slots": json.dumps(["address", "customer_name", "phone_number"]),
                "optional_slots": json.dumps(["package_name", "speed"]),
                "next_action": "ask_address_or_show_packages",
            },
            {
                "intent_code": "ask_price",
                "description": "Customer asks price",
                "required_slots": "[]",
                "optional_slots": json.dumps(["speed"]),
                "next_action": "show_price",
            },
            {
                "intent_code": "ask_coverage",
                "description": "Customer asks coverage",
                "required_slots": json.dumps(["address"]),
                "optional_slots": "[]",
                "next_action": "ask_or_validate_address",
            },
            {
                "intent_code": "ask_payment_method",
                "description": "Customer asks payment",
                "required_slots": "[]",
                "optional_slots": json.dumps(["payment_method"]),
                "next_action": "show_payment_methods",
            },
            {
                "intent_code": "ask_package",
                "description": "Customer asks packages",
                "required_slots": "[]",
                "optional_slots": "[]",
                "next_action": "show_package_list",
            },
        ],
    }


class ISPCSAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = ISPCSAgent(build_catalog())

    def test_matches_price_with_suffix_and_slang(self) -> None:
        response = self.agent.answer("harganya paket 30mb berapaan kak?")

        self.assertEqual(response.language, "id")
        self.assertEqual(response.intent.intent_code, "ask_price")
        self.assertNotIn("Maaf Kak", response.reply_text)

    def test_matches_coverage_from_network_phrase(self) -> None:
        response = self.agent.answer("di cigadung udah masuk jaringan belum?")

        self.assertEqual(response.intent.intent_code, "ask_coverage")
        self.assertNotIn("Maaf Kak", response.reply_text)

    def test_matches_sundanese_package_sample(self) -> None:
        response = self.agent.answer("paketna aya naon wae kang?")

        self.assertEqual(response.language, "su")
        self.assertEqual(response.intent.intent_code, "ask_package")
        self.assertNotIn("Maaf Kak", response.reply_text)

    def test_sample_only_follow_up_gets_specific_reply(self) -> None:
        response = self.agent.answer("teknisinya sudah sampai mana ya?")

        self.assertEqual(response.intent.intent_code, "follow_up_installation")
        self.assertNotIn("Maaf Kak", response.reply_text)

    def test_memory_fills_area_followup_before_reclassifying_intent(self) -> None:
        first_response = self.agent.answer("Saya mau pasang internet, bisa?")

        self.assertEqual(first_response.intent.intent_code, "ask_installation")
        self.assertIn("address", first_response.memory_update["waiting_for"])

        followup_response = self.agent.answer(
            "Soreang",
            conversation_state=first_response.memory_update,
        )

        self.assertEqual(followup_response.intent.intent_code, "ask_installation")
        self.assertEqual(followup_response.memory_update["collected_slots"]["address"], "Soreang")
        self.assertIn("nama pelanggan", followup_response.reply_text)

    def test_memory_extracts_name_phone_and_address_from_combined_followup(self) -> None:
        state = {
            "current_intent": "ask_installation",
            "stage": "collecting_slots",
            "waiting_for": ["customer_name", "phone_number", "address"],
            "collected_slots": {},
            "next_action": "ask_address_or_show_packages",
        }

        response = self.agent.answer("Dikdik, 087777777, Bandung", conversation_state=state)

        self.assertEqual(response.intent.intent_code, "ask_installation")
        self.assertEqual(response.memory_update["collected_slots"]["customer_name"], "Dikdik")
        self.assertEqual(response.memory_update["collected_slots"]["phone_number"], "087777777")
        self.assertEqual(response.memory_update["collected_slots"]["address"], "Bandung")
        self.assertNotIn("Maaf Kak", response.reply_text)


if __name__ == "__main__":
    unittest.main()
