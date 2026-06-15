from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore


class SQLitePackageCatalogTests(unittest.TestCase):
    def _new_store(self, temp_dir: str) -> SQLiteChatStore:
        db_path = str(Path(temp_dir) / "chat.sqlite3")
        return SQLiteChatStore(Settings(chat_database_path=db_path))

    def test_initialize_seeds_default_internet_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self._new_store(temp_dir)

            store.initialize()
            packages = store.list_internet_packages()

        package_names = {package["package_name"] for package in packages}
        self.assertEqual(len(packages), 4)
        self.assertIn("Paket Hemat", package_names)
        self.assertIn("Paket Keluarga", package_names)
        self.assertIn("Paket Premium", package_names)
        self.assertIn("Paket Office", package_names)

    def test_initialize_seeds_coverage_and_payment_catalogs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self._new_store(temp_dir)

            store.initialize()
            catalog = store.get_intent_agent_catalog()

        coverage_names = {area["area_name"] for area in catalog["coverage_areas"]}
        payment_names = {method["method_name"] for method in catalog["payment_methods"]}
        self.assertIn("Soreang", coverage_names)
        self.assertIn("Conblong", coverage_names)
        self.assertIn("QRIS", payment_names)
        self.assertIn("Transfer Bank", payment_names)

    def test_scoped_tables_have_client_and_device_columns(self) -> None:
        scoped_tables = {
            "messages",
            "stock_products",
            "internet_packages",
            "coverage_areas",
            "payment_methods",
            "intents",
            "languages",
            "keywords",
            "entities",
            "entity_keywords",
            "sample_utterances",
            "normalization_rules",
            "intent_mappings",
            "conversation_states",
            "unprocessed_questions",
            "conversation_logs",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self._new_store(temp_dir)
            store.initialize()

            with store._connect() as conn:
                table_columns = {
                    table: {
                        str(row["name"])
                        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                    }
                    for table in scoped_tables
                }

        for table, columns in table_columns.items():
            self.assertIn("client_id", columns, table)
            self.assertIn("device_id", columns, table)

    def test_device_scoped_catalog_and_stock_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self._new_store(temp_dir)
            store.initialize()
            store.create_account(name="ISP A", slug="isp-a")
            client = store.create_client(account_slug="isp-a", name="Client A")
            device_one = store.register_device(
                client_id=client["id"],
                device_identifier="device-a-1",
                device_name="Device A1",
                outbound_token=None,
            )
            device_two = store.register_device(
                client_id=client["id"],
                device_identifier="device-a-2",
                device_name="Device A2",
                outbound_token=None,
            )

            packages = store.list_internet_packages(
                client_id=client["id"],
                device_id=device_one["id"],
            )
            stock_one = store.upsert_stock_product(
                client_id=client["id"],
                device_id=device_one["id"],
                product_name="Router Fiber",
                stock=3,
            )
            stock_two = store.upsert_stock_product(
                client_id=client["id"],
                device_id=device_two["id"],
                product_name="Router Fiber",
                stock=7,
            )
            device_one_stock = store.list_stock_products(
                client_id=client["id"],
                device_id=device_one["id"],
            )

        self.assertEqual(len(packages), 4)
        self.assertEqual({package["device_id"] for package in packages}, {device_one["id"]})
        self.assertNotEqual(stock_one["id"], stock_two["id"])
        self.assertEqual(device_one_stock[0]["stock"], 3)
        self.assertEqual(device_one_stock[0]["device_id"], device_one["id"])

    def test_legacy_unique_constraints_are_migrated_to_device_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chat.sqlite3")
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE internet_packages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        package_code TEXT NOT NULL UNIQUE,
                        package_name TEXT NOT NULL,
                        speed_mbps INTEGER NOT NULL,
                        monthly_price INTEGER NOT NULL,
                        installation_fee INTEGER NOT NULL DEFAULT 0,
                        installation_fee_label TEXT,
                        areas TEXT NOT NULL DEFAULT '[]',
                        benefits TEXT NOT NULL DEFAULT '[]',
                        is_active INTEGER NOT NULL DEFAULT 1,
                        sort_order INTEGER NOT NULL DEFAULT 100,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE stock_products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER NOT NULL,
                        product_name TEXT NOT NULL,
                        product_type TEXT,
                        stock INTEGER NOT NULL DEFAULT 0,
                        metadata TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (client_id, product_name, product_type)
                    );
                    """
                )

            store = SQLiteChatStore(Settings(chat_database_path=db_path))
            store.initialize()
            store.create_account(name="ISP Legacy", slug="isp-legacy")
            client = store.create_client(account_slug="isp-legacy", name="Legacy Client")
            device_one = store.register_device(
                client_id=client["id"],
                device_identifier="legacy-device-1",
                device_name="Legacy Device 1",
                outbound_token=None,
            )
            device_two = store.register_device(
                client_id=client["id"],
                device_identifier="legacy-device-2",
                device_name="Legacy Device 2",
                outbound_token=None,
            )

            packages_one = store.list_internet_packages(
                client_id=client["id"],
                device_id=device_one["id"],
            )
            packages_two = store.list_internet_packages(
                client_id=client["id"],
                device_id=device_two["id"],
            )
            stock_one = store.upsert_stock_product(
                client_id=client["id"],
                device_id=device_one["id"],
                product_name="Router Legacy",
                stock=2,
            )
            stock_two = store.upsert_stock_product(
                client_id=client["id"],
                device_id=device_two["id"],
                product_name="Router Legacy",
                stock=5,
            )

        self.assertEqual(len(packages_one), 4)
        self.assertEqual(len(packages_two), 4)
        self.assertEqual({package["device_id"] for package in packages_one}, {device_one["id"]})
        self.assertEqual({package["device_id"] for package in packages_two}, {device_two["id"]})
        self.assertNotEqual(stock_one["id"], stock_two["id"])

    def test_legacy_intent_foreign_keys_are_rebuilt_after_parent_scope_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chat.sqlite3")
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE intents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        intent_code TEXT NOT NULL UNIQUE,
                        intent_name TEXT NOT NULL,
                        description TEXT
                    );

                    CREATE TABLE conversation_states (
                        conversation_id INTEGER PRIMARY KEY,
                        current_intent TEXT,
                        stage TEXT NOT NULL DEFAULT 'idle',
                        waiting_for TEXT NOT NULL DEFAULT '[]',
                        collected_slots TEXT NOT NULL DEFAULT '{}',
                        last_bot_question TEXT,
                        next_action TEXT,
                        expires_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                        FOREIGN KEY (current_intent) REFERENCES intents (intent_code)
                    );

                    CREATE TABLE unprocessed_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER NOT NULL,
                        conversation_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL UNIQUE,
                        language TEXT NOT NULL,
                        message_text TEXT NOT NULL,
                        normalized_text TEXT,
                        detected_intent_code TEXT,
                        confidence REAL NOT NULL DEFAULT 0,
                        reason TEXT NOT NULL,
                        candidates TEXT,
                        entities TEXT,
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK(status IN ('pending', 'mapped', 'ignored')),
                        mapped_intent_code TEXT,
                        mapped_type TEXT,
                        reviewer_notes TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        resolved_at TEXT,
                        FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                        FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
                        FOREIGN KEY (mapped_intent_code) REFERENCES intents (intent_code)
                    );
                    """
                )

            store = SQLiteChatStore(Settings(chat_database_path=db_path))
            store.initialize()
            stored = store.save_incoming_message(
                {
                    "sender": "08123456789",
                    "name": "Legacy FK Tester",
                    "message": "tes paket internet",
                    "device": "legacy-fk-device",
                }
            )

            store.upsert_conversation_state(
                conversation_id=stored.conversation_id,
                state={
                    "current_intent": "ask_package",
                    "current_topic": "package_info",
                    "waiting_for": [],
                    "collected_slots": {},
                    "last_bot_question": "Ada paket apa?",
                },
            )
            store.save_unprocessed_question(
                stored_message=stored,
                analysis={
                    "language": "id",
                    "intent": {"intent_code": "unknown", "confidence": 0.1},
                    "candidates": [],
                    "entities": [],
                },
                reason="unknown_intent",
            )
            question = store.list_unprocessed_questions(limit=1)[0]
            mapped = store.map_unprocessed_question(
                question_id=int(question["id"]),
                intent_code="ask_package",
                mapping_type="sample",
            )

        self.assertEqual(mapped["status"], "mapped")
        self.assertEqual(mapped["mapped_intent_code"], "ask_package")


if __name__ == "__main__":
    unittest.main()
