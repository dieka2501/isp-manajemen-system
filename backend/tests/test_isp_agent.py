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
        "internet_packages": [
            {
                "package_code": "hemat",
                "package_name": "Paket Hemat",
                "speed_mbps": 20,
                "monthly_price": 150000,
                "installation_fee": 150000,
                "installation_fee_label": "Rp 150.000",
                "areas": ["Soreang", "Bandung", "Cangkuang"],
                "benefits": ["unlimited", "router dipinjamkan"],
                "is_active": 1,
                "sort_order": 10,
                "notes": None,
            },
            {
                "package_code": "keluarga",
                "package_name": "Paket Keluarga",
                "speed_mbps": 30,
                "monthly_price": 200000,
                "installation_fee": 150000,
                "installation_fee_label": "Rp 150.000",
                "areas": ["Soreang", "Bandung", "Cangkuang"],
                "benefits": ["cocok 3-5 perangkat"],
                "is_active": 1,
                "sort_order": 20,
                "notes": None,
            },
            {
                "package_code": "premium",
                "package_name": "Paket Premium",
                "speed_mbps": 50,
                "monthly_price": 300000,
                "installation_fee": 0,
                "installation_fee_label": "Rp 0 promo",
                "areas": ["Soreang", "Bandung"],
                "benefits": ["cocok kerja", "streaming", "gaming ringan"],
                "is_active": 1,
                "sort_order": 30,
                "notes": None,
            },
            {
                "package_code": "office",
                "package_name": "Paket Office",
                "speed_mbps": 100,
                "monthly_price": 500000,
                "installation_fee": 0,
                "installation_fee_label": "Rp 0 promo",
                "areas": ["Kab Bandung", "Kota Bandung", "Cimahi", "Bandung Barat"],
                "benefits": ["cocok untuk kantor"],
                "is_active": 1,
                "sort_order": 40,
                "notes": None,
            },
        ],
        "payment_methods": [
            {
                "method_code": "bank_transfer",
                "method_name": "Transfer Bank",
                "is_available": 1,
                "notes": None,
                "sort_order": 10,
            },
            {
                "method_code": "qris",
                "method_name": "QRIS",
                "is_available": 1,
                "notes": None,
                "sort_order": 20,
            },
            {
                "method_code": "cash",
                "method_name": "Cash",
                "is_available": 1,
                "notes": None,
                "sort_order": 30,
            },
            {
                "method_code": "ewallet",
                "method_name": "E-wallet",
                "is_available": 1,
                "notes": None,
                "sort_order": 40,
            },
        ],
        "coverage_areas": [
            {
                "area_code": "conblong",
                "area_name": "Conblong",
                "city": "Kota Bandung",
                "district": "Coblong",
                "coverage_status": "covered",
                "notes": None,
                "is_active": 1,
                "sort_order": 10,
            },
            {
                "area_code": "soreang",
                "area_name": "Soreang",
                "city": "Kab Bandung",
                "district": "Soreang",
                "coverage_status": "covered",
                "notes": None,
                "is_active": 1,
                "sort_order": 20,
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
        self.assertIn("Paket Keluarga", response.reply_text)
        self.assertNotIn("Paket Hemat", response.reply_text)
        self.assertNotIn("Maaf Kak", response.reply_text)
        self.assertNotIn("nama pelanggan", response.reply_text.lower())
        self.assertNotIn("nomor hp", response.reply_text.lower())

    def test_package_and_price_overview_stays_in_soft_package_flow(self) -> None:
        response = self.agent.answer("Saya ingin tahu paket dan harganya.")

        self.assertEqual(response.intent.intent_code, "ask_package")
        self.assertIn("Paket Hemat", response.reply_text)
        self.assertIn("Rp 150.000/bulan", response.reply_text)
        self.assertIn("Paket Office", response.reply_text)
        self.assertNotIn("nama pelanggan", response.reply_text.lower())
        self.assertNotIn("nomor hp", response.reply_text.lower())
        self.assertIn("kebutuhan", response.reply_text.lower())

    def test_package_overview_filters_by_area_when_area_is_available(self) -> None:
        response = self.agent.answer("paket di Soreang apa aja?")

        self.assertEqual(response.intent.intent_code, "ask_package")
        self.assertIn("Untuk area soreang", response.reply_text)
        self.assertIn("Paket Premium", response.reply_text)
        self.assertNotIn("Paket Office", response.reply_text)

    def test_package_price_followup_uses_speed_specific_package(self) -> None:
        response = self.agent.answer(
            "Yang 30 Mbps berapa?",
            conversation_state={
                "current_intent": "ask_package",
                "current_topic": "package_info",
                "waiting_for": [],
                "collected_slots": {},
                "last_bot_response": "Ada Paket Hemat, Keluarga, Premium, dan Office.",
            },
        )

        self.assertEqual(response.intent.intent_code, "ask_price")
        self.assertIn("Paket Keluarga", response.reply_text)
        self.assertIn("Rp 200.000/bulan", response.reply_text)
        self.assertNotIn("Paket Hemat", response.reply_text)

    def test_matches_coverage_from_network_phrase(self) -> None:
        response = self.agent.answer("di cigadung udah masuk jaringan belum?")

        self.assertEqual(response.intent.intent_code, "ask_coverage")
        self.assertNotIn("Maaf Kak", response.reply_text)

    def test_coverage_followup_uses_coverage_topic(self) -> None:
        response = self.agent.answer(
            "Conblong",
            conversation_state={
                "current_intent": "ask_coverage",
                "current_topic": "coverage_check",
                "waiting_for": ["address"],
                "collected_slots": {"city": "Bandung"},
                "last_bot_response": "Boleh sebutkan kecamatan atau kelurahannya dulu Kak.",
            },
        )

        self.assertEqual(response.intent.intent_code, "ask_coverage")
        self.assertIn("sudah tercover", response.reply_text)
        self.assertNotIn("alamat Conblong saya catat", response.reply_text)

    def test_payment_followup_does_not_repeat_full_payment_list(self) -> None:
        response = self.agent.answer(
            "Kalau QRIS bisa?",
            conversation_state={
                "current_intent": "ask_payment_method",
                "current_topic": "payment",
                "waiting_for": [],
                "collected_slots": {},
                "last_bot_response": "Bisa Kak, pembayaran bisa transfer bank, QRIS, cash, atau e-wallet.",
            },
        )

        self.assertEqual(response.intent.intent_code, "ask_payment_method")
        self.assertIn("QRIS", response.reply_text)
        self.assertNotIn("Transfer Bank, QRIS, Cash", response.reply_text)

    def test_unknown_followup_uses_previous_package_topic(self) -> None:
        response = self.agent.answer(
            "Kan tadi udah dijawab",
            conversation_state={
                "current_intent": "ask_package",
                "current_topic": "package_info",
                "waiting_for": [],
                "collected_slots": {},
                "last_bot_response": "Sementara paket yang tersedia: Paket Hemat, Keluarga, Premium, Office.",
            },
        )

        self.assertEqual(response.intent.intent_code, "unknown")
        self.assertIn("paket", response.reply_text.lower())
        self.assertNotIn("belum nyambung", response.reply_text.lower())
        self.assertEqual(response.memory_update["current_topic"], "package_info")

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
        self.assertEqual(first_response.memory_update["waiting_for"], ["address"])
        self.assertNotIn("nama pelanggan", first_response.reply_text.lower())
        self.assertNotIn("nomor hp", first_response.reply_text.lower())

        followup_response = self.agent.answer(
            "Soreang",
            conversation_state=first_response.memory_update,
        )

        self.assertEqual(followup_response.intent.intent_code, "ask_installation")
        self.assertEqual(followup_response.memory_update["collected_slots"]["address"], "Soreang")
        self.assertNotIn("nama pelanggan", followup_response.reply_text.lower())
        self.assertNotIn("nomor hp", followup_response.reply_text.lower())

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

    def test_confirm_package_sets_order_state(self) -> None:
        response = self.agent.answer("Saya ambil paket 50 Mbps.")

        self.assertEqual(response.intent.intent_code, "choose_package")
        self.assertIn("Paket Premium 50 Mbps", response.reply_text)
        self.assertIn("nama", response.reply_text.lower())
        self.assertEqual(response.memory_update["current_topic"], "order_confirmation")
        self.assertIn("speed", response.memory_update["collected_slots"])


if __name__ == "__main__":
    unittest.main()
