from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.provider_dashboard.dry_run import DryRunExecuteRequest, DryRunTestLab
from app.services.chat_store import SQLiteChatStore
from test_isp_agent import build_catalog


class ProviderDryRunTests(unittest.TestCase):
    def _settings(self, database_path: str = ":memory:") -> Settings:
        return Settings(
            chat_database_path=database_path,
            billing_sample_xlsx_path="",
            openai_api_key="",
            llm_response_enabled=False,
            registration_offer_message_threshold=5,
        )

    def _mock_store(self) -> Mock:
        catalog = build_catalog()
        store = Mock()
        store.list_clients.return_value = [
            {
                "id": 7,
                "name": "ISP Example",
                "account_name": "Provider Account",
                "account_slug": "provider-account",
                "is_active": 1,
                "api_token": "must-never-be-returned",
            }
        ]
        store.list_client_devices.return_value = [
            {
                "id": 11,
                "client_id": 7,
                "device_identifier": "cs-one",
                "device_name": "Customer Service 1",
            }
        ]
        store.list_intents_for_mapping.return_value = catalog["intents"]
        store.get_intent_agent_catalog.return_value = catalog
        return store

    def test_compare_candidate_is_temporary_and_explains_recognition_change(self) -> None:
        store = self._mock_store()
        payload = DryRunExecuteRequest.model_validate(
            {
                "client_id": 7,
                "device_id": 11,
                "message": "zeta orbit khusus pelanggan",
                "mapping_mode": "compare",
                "candidate_mapping": {
                    "intent_code": "ask_package",
                    "mapping_type": "both",
                    "sample_utterance": "zeta orbit khusus pelanggan",
                    "keyword": "zeta orbit",
                    "weight": 8,
                },
                "pipeline": {
                    "execution": "native_only",
                    "llm_enabled": False,
                    "knowledge_retrieval_enabled": True,
                    "registration_invitation_enabled": False,
                },
                "expected": {"expected_intent": "ask_package"},
            }
        )

        result = DryRunTestLab(self._settings(), store=store).execute(payload)

        report = result["report"]
        self.assertEqual(
            report["variants"]["before"]["native_analysis"]["intent"]["intent_code"],
            "unknown",
        )
        self.assertEqual(
            report["variants"]["after"]["native_analysis"]["intent"]["intent_code"],
            "ask_package",
        )
        self.assertTrue(report["conclusion"]["recognition_changed"])
        self.assertFalse(report["production_mutation"])
        self.assertFalse(report["external_send"])
        original_samples = store.get_intent_agent_catalog.return_value["sample_utterances"]
        self.assertFalse(any(item.get("utterance") == "zeta orbit khusus pelanggan" for item in original_samples))

    def test_context_does_not_expose_client_api_token_and_rejects_cross_client_device(self) -> None:
        store = self._mock_store()
        lab = DryRunTestLab(self._settings(), store=store)

        context = lab.context(client_id=7, device_id=11)

        self.assertNotIn("api_token", context["clients"][0])
        with self.assertRaisesRegex(ValueError, "does not belong"):
            lab.context(client_id=7, device_id=999)

    def test_compare_identifies_waiting_slot_memory_priority(self) -> None:
        store = self._mock_store()
        payload = DryRunExecuteRequest.model_validate(
            {
                "client_id": 7,
                "device_id": 11,
                "message": "Kak, saya mau daftar",
                "state_source": "custom",
                "initial_state": {
                    "current_intent": "ask_installation",
                    "waiting_for": ["address"],
                    "collected_slots": {},
                },
                "mapping_mode": "compare",
                "candidate_mapping": {
                    "intent_code": "ask_installation",
                    "mapping_type": "both",
                    "sample_utterance": "Kak, saya mau daftar",
                    "keyword": "mau daftar",
                    "weight": 8,
                },
                "pipeline": {"execution": "native_only", "llm_enabled": False},
            }
        )

        report = DryRunTestLab(self._settings(), store=store).execute(payload)["report"]

        self.assertEqual(
            report["variants"]["after"]["slot_processing"]["classification_source"],
            "conversation_memory",
        )
        self.assertEqual(
            report["conclusion"]["suspected_layer"],
            ["conversation_state", "slot_priority"],
        )
        self.assertIn("before fresh intent ranking", report["conclusion"]["recognition_summary"])

    def test_sanitized_copy_redacts_contact_and_workflow_urls(self) -> None:
        store = self._mock_store()
        payload = DryRunExecuteRequest.model_validate(
            {
                "client_id": 7,
                "device_id": 11,
                "message": "Hubungi 081234567890 atau test@example.com https://example.com/private",
                "business_state": {
                    "registration_status": "registered",
                    "registration_url": "https://example.com/register/secret",
                    "payment_url": "https://example.com/payment/secret",
                    "invitation_already_exists": True,
                },
                "pipeline": {"execution": "native_only", "llm_enabled": False},
            }
        )

        result = DryRunTestLab(self._settings(), store=store).execute(payload)
        copied = result["audit_summary"]

        self.assertNotIn("081234567890", copied)
        self.assertNotIn("test@example.com", copied)
        self.assertNotIn("https://example.com", copied)
        self.assertIn("[PHONE_REDACTED]", copied)
        self.assertIn("[EMAIL_REDACTED]", copied)
        self.assertIn("[URL_REDACTED]", copied)

    def test_execution_leaves_sqlite_file_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = str(Path(temp_dir) / "dry-run.sqlite3")
            settings = self._settings(database_path)
            store = SQLiteChatStore(settings)
            store.initialize()
            context = DryRunTestLab(settings, store=store).context()
            client_id = context["selected"]["client_id"]
            device_id = context["selected"]["device_id"]
            with sqlite3.connect(database_path) as connection:
                before = "\n".join(connection.iterdump())

            result = DryRunTestLab(settings, store=store).execute(
                DryRunExecuteRequest.model_validate(
                    {
                        "client_id": client_id,
                        "device_id": device_id,
                        "message": "Kak, paketnya ada apa saja?",
                        "pipeline": {"execution": "native_only", "llm_enabled": False},
                    }
                )
            )
            with sqlite3.connect(database_path) as connection:
                after = "\n".join(connection.iterdump())

            self.assertEqual(before, after)
            self.assertTrue(
                result["report"]["variants"]["single"]["planned_side_effects"]
                ["dry_run_execution"]["all_database_writes_blocked"]
            )
            self.assertTrue(
                result["report"]["variants"]["single"]["planned_side_effects"]
                ["dry_run_execution"]["fonnte_send_blocked"]
            )


if __name__ == "__main__":
    unittest.main()
