from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.openai_learning import OpenAILearningHelper


class OpenAILearningHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.helper = OpenAILearningHelper(Settings(openai_api_key="test-key"))
        self.intents = [
            {"intent_code": "ask_coverage", "intent_name": "Cek coverage"},
            {"intent_code": "provide_address", "intent_name": "Memberikan alamat"},
        ]

    def test_normalizes_valid_suggestion(self) -> None:
        suggestion = self.helper._normalize_suggestion(
            {
                "intent_code": "provide_address",
                "mapping_type": "both",
                "keyword": "Soreang ka",
                "normalized_keyword": "soreang",
                "weight": 12,
                "reason": "Area pemasangan.",
            },
            self.intents,
        )

        self.assertEqual(suggestion["intent_code"], "provide_address")
        self.assertEqual(suggestion["mapping_type"], "both")
        self.assertEqual(suggestion["weight"], 10)
        self.assertEqual(suggestion["normalized_keyword"], "soreang")

    def test_invalid_intent_is_forced_to_ignore(self) -> None:
        suggestion = self.helper._normalize_suggestion(
            {
                "intent_code": "made_up",
                "mapping_type": "keyword",
                "keyword": "x",
                "normalized_keyword": "x",
                "weight": 4,
                "reason": "Tidak ada intent cocok.",
            },
            self.intents,
        )

        self.assertIsNone(suggestion["intent_code"])
        self.assertEqual(suggestion["mapping_type"], "ignore")


if __name__ == "__main__":
    unittest.main()
