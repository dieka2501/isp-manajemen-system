from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.isp_agent import ISPCSAgent
from app.services.knowledge_retrieval import KnowledgeRetriever
from app.services.llm_response import LLMResponseGenerator
from test_isp_agent import build_catalog


class LLMOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_catalog()
        self.agent = ISPCSAgent(self.catalog)
        self.retriever = KnowledgeRetriever(self.catalog)

    def test_retriever_filters_package_by_speed_followup(self) -> None:
        response = self.agent.answer(
            "Yang 30 Mbps berapa?",
            conversation_state={"current_topic": "package_info"},
        )

        knowledge = self.retriever.retrieve(
            user_message="Yang 30 Mbps berapa?",
            agent_response=response,
            conversation_state={"current_topic": "package_info"},
        )

        package_names = [
            package["package_name"]
            for package in knowledge["data"]["packages"]
        ]
        self.assertEqual(package_names, ["Paket Keluarga"])

    def test_retriever_filters_payment_followup_to_qris(self) -> None:
        response = self.agent.answer(
            "Kalau QRIS bisa?",
            conversation_state={"current_topic": "payment"},
        )

        knowledge = self.retriever.retrieve(
            user_message="Kalau QRIS bisa?",
            agent_response=response,
            conversation_state={"current_topic": "payment"},
        )

        methods = knowledge["data"]["payment_methods"]
        self.assertEqual(len(methods), 1)
        self.assertEqual(methods[0]["method_code"], "qris")

    def test_prompt_includes_knowledge_guardrails_and_native_fallback(self) -> None:
        response = self.agent.answer("Paketnya ada apa aja?")
        knowledge = self.retriever.retrieve(
            user_message="Paketnya ada apa aja?",
            agent_response=response,
            conversation_state=None,
        )
        generator = LLMResponseGenerator(
            Settings(openai_api_key="", llm_response_enabled=False)
        )

        prompt = generator.build_prompt(
            user_message="Paketnya ada apa aja?",
            agent_response=response,
            conversation_state=None,
            knowledge=knowledge,
            native_reply=response.reply_text,
        )

        self.assertIn("ONLY the facts in the Knowledge section", prompt)
        self.assertIn("Paket Hemat", prompt)
        self.assertIn("native_fallback_reply", prompt)


if __name__ == "__main__":
    unittest.main()
