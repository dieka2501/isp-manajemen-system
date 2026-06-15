from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.config import Settings
from app.services.intent_seed import (
    DEFAULT_COVERAGE_AREAS,
    DEFAULT_INTENT_MAPPINGS,
    DEFAULT_INTENT_SEED,
    DEFAULT_INTERNET_PACKAGES,
    DEFAULT_PAYMENT_METHODS,
)

DEFAULT_CATALOG_EXTERNAL_REF = "__default_catalog__"
DEFAULT_CATALOG_DEVICE_IDENTIFIER = "__default_catalog_device__"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "account"


def _normalize_search_text(value: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in value).split()
    )


@dataclass(frozen=True)
class DeviceContext:
    account_id: int
    account_name: str
    account_slug: str
    client_id: int
    client_name: str
    client_token: str
    device_id: int
    device_identifier: str
    device_name: str | None
    outbound_token: str | None


@dataclass(frozen=True)
class StoredIncomingMessage:
    conversation_id: int
    message_id: int
    sender_number: str
    sender_name: str | None
    message_text: str
    device: DeviceContext


@dataclass(frozen=True)
class StockMatch:
    product_id: int
    product_name: str
    product_type: str
    stock: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_type": self.product_type,
            "stock": self.stock,
        }


class SQLiteChatStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = Path(settings.chat_database_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    external_ref TEXT,
                    api_token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_identifier TEXT NOT NULL UNIQUE,
                    device_name TEXT,
                    outbound_token TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    sender_number TEXT NOT NULL,
                    sender_name TEXT,
                    last_message_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, sender_number)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('incoming', 'outgoing')),
                    message_text TEXT NOT NULL,
                    matched_keywords TEXT,
                    matched_product_name TEXT,
                    reply_text TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS stock_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    product_type TEXT,
                    stock INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, product_name, product_type)
                );

                CREATE TABLE IF NOT EXISTS internet_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    package_code TEXT NOT NULL,
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
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, package_code)
                );

                CREATE TABLE IF NOT EXISTS coverage_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    area_code TEXT NOT NULL,
                    area_name TEXT NOT NULL,
                    city TEXT,
                    district TEXT,
                    coverage_status TEXT NOT NULL DEFAULT 'unknown'
                        CHECK(coverage_status IN ('covered', 'partial', 'not_covered', 'unknown')),
                    notes TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, area_code)
                );

                CREATE TABLE IF NOT EXISTS payment_methods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    method_code TEXT NOT NULL,
                    method_name TEXT NOT NULL,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, method_code)
                );

                CREATE TABLE IF NOT EXISTS intents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    intent_code TEXT NOT NULL,
                    intent_name TEXT NOT NULL,
                    description TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, intent_code)
                );

                CREATE TABLE IF NOT EXISTS languages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    lang_code TEXT NOT NULL,
                    lang_name TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, lang_code)
                );

                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    intent_code TEXT NOT NULL,
                    lang_code TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    normalized_keyword TEXT,
                    formality_level TEXT,
                    weight INTEGER DEFAULT 1,
                    notes TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, intent_code, lang_code, keyword)
                );

                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    entity_code TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    description TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, entity_code)
                );

                CREATE TABLE IF NOT EXISTS entity_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    entity_code TEXT NOT NULL,
                    lang_code TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    normalized_keyword TEXT,
                    notes TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, entity_code, lang_code, keyword)
                );

                CREATE TABLE IF NOT EXISTS sample_utterances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    intent_code TEXT NOT NULL,
                    lang_code TEXT NOT NULL,
                    utterance TEXT NOT NULL,
                    formality_level TEXT,
                    expected_entities TEXT,
                    notes TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, intent_code, lang_code, utterance)
                );

                CREATE TABLE IF NOT EXISTS normalization_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    lang_code TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    normalized_text TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, lang_code, source_text)
                );

                CREATE TABLE IF NOT EXISTS intent_mappings (
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    intent_code TEXT NOT NULL,
                    description TEXT,
                    required_slots TEXT NOT NULL DEFAULT '[]',
                    optional_slots TEXT NOT NULL DEFAULT '[]',
                    next_action TEXT,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    PRIMARY KEY (client_id, device_id, intent_code)
                );

                CREATE TABLE IF NOT EXISTS conversation_states (
                    conversation_id INTEGER PRIMARY KEY,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    current_intent TEXT,
                    current_topic TEXT,
                    stage TEXT NOT NULL DEFAULT 'idle',
                    waiting_for TEXT NOT NULL DEFAULT '[]',
                    collected_slots TEXT NOT NULL DEFAULT '{}',
                    last_bot_question TEXT,
                    last_user_message TEXT,
                    last_bot_response TEXT,
                    next_action TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, conversation_id)
                );

                CREATE TABLE IF NOT EXISTS unprocessed_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
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
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    message_id INTEGER,
                    phone_number TEXT NOT NULL,
                    user_message TEXT NOT NULL,
                    detected_intent TEXT,
                    confidence REAL,
                    entities_json TEXT,
                    state_before_json TEXT,
                    state_after_json TEXT,
                    knowledge_json TEXT,
                    bot_response TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                    FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_clients_account_id ON clients (account_id);
                CREATE INDEX IF NOT EXISTS idx_devices_client_id ON devices (client_id);
                CREATE INDEX IF NOT EXISTS idx_conversations_client_id ON conversations (client_id);
                CREATE INDEX IF NOT EXISTS idx_conversations_device_id ON conversations (device_id);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages (created_at);
                CREATE INDEX IF NOT EXISTS idx_stock_products_client_id
                    ON stock_products (client_id);
                CREATE INDEX IF NOT EXISTS idx_stock_products_name
                    ON stock_products (product_name);
                CREATE INDEX IF NOT EXISTS idx_internet_packages_active_sort
                    ON internet_packages (is_active, sort_order);
                CREATE INDEX IF NOT EXISTS idx_coverage_areas_active_sort
                    ON coverage_areas (is_active, sort_order);
                CREATE INDEX IF NOT EXISTS idx_payment_methods_available_sort
                    ON payment_methods (is_available, sort_order);
                CREATE INDEX IF NOT EXISTS idx_keywords_intent_lang
                    ON keywords (intent_code, lang_code);
                CREATE INDEX IF NOT EXISTS idx_keywords_normalized_keyword
                    ON keywords (normalized_keyword);
                CREATE INDEX IF NOT EXISTS idx_entity_keywords_entity_lang
                    ON entity_keywords (entity_code, lang_code);
                CREATE INDEX IF NOT EXISTS idx_sample_utterances_intent_lang
                    ON sample_utterances (intent_code, lang_code);
                CREATE INDEX IF NOT EXISTS idx_normalization_rules_lang
                    ON normalization_rules (lang_code);
                CREATE INDEX IF NOT EXISTS idx_unprocessed_questions_status
                    ON unprocessed_questions (status, created_at);
                CREATE INDEX IF NOT EXISTS idx_unprocessed_questions_client
                    ON unprocessed_questions (client_id, status);
                CREATE INDEX IF NOT EXISTS idx_conversation_logs_conversation
                    ON conversation_logs (conversation_id, created_at);
                """
            )
            self._ensure_schema_migrations(conn)
            default_client_id, default_device_id = self._ensure_default_catalog_scope(conn)
            self._seed_default_catalog_for_scope(
                conn,
                client_id=default_client_id,
                device_id=default_device_id,
            )

    def _ensure_default_catalog_scope(self, conn: sqlite3.Connection) -> tuple[int, int]:
        now = _utc_now()
        account = conn.execute(
            "SELECT id, name, slug FROM accounts WHERE slug = ?",
            (self.settings.chat_auto_account_slug,),
        ).fetchone()
        if not account:
            cursor = conn.execute(
                """
                INSERT INTO accounts (name, slug, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self.settings.chat_auto_account_name,
                    self.settings.chat_auto_account_slug,
                    now,
                    now,
                ),
            )
            account = conn.execute(
                "SELECT id, name, slug FROM accounts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        client = conn.execute(
            """
            SELECT id
            FROM clients
            WHERE account_id = ? AND external_ref = ?
            """,
            (account["id"], DEFAULT_CATALOG_EXTERNAL_REF),
        ).fetchone()
        if not client:
            cursor = conn.execute(
                """
                INSERT INTO clients (
                    account_id,
                    name,
                    external_ref,
                    api_token,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account["id"],
                    "Default Catalog Client",
                    DEFAULT_CATALOG_EXTERNAL_REF,
                    secrets.token_urlsafe(24),
                    now,
                    now,
                ),
            )
            client_id = int(cursor.lastrowid)
        else:
            client_id = int(client["id"])

        device = conn.execute(
            """
            SELECT id
            FROM devices
            WHERE device_identifier = ?
            """,
            (DEFAULT_CATALOG_DEVICE_IDENTIFIER,),
        ).fetchone()
        if not device:
            cursor = conn.execute(
                """
                INSERT INTO devices (
                    client_id,
                    device_identifier,
                    device_name,
                    outbound_token,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    DEFAULT_CATALOG_DEVICE_IDENTIFIER,
                    "Default Catalog Device",
                    None,
                    now,
                    now,
                ),
            )
            device_id = int(cursor.lastrowid)
        else:
            device_id = int(device["id"])

        return client_id, device_id

    def _seed_intent_catalog(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int,
        device_id: int,
    ) -> None:
        seed_tables = {
            "intents": ("intent_code", "intent_name", "description"),
            "languages": ("lang_code", "lang_name"),
            "entities": ("entity_code", "entity_name", "description"),
            "keywords": (
                "intent_code",
                "lang_code",
                "keyword",
                "normalized_keyword",
                "formality_level",
                "weight",
                "notes",
            ),
            "entity_keywords": (
                "entity_code",
                "lang_code",
                "keyword",
                "normalized_keyword",
                "notes",
            ),
            "sample_utterances": (
                "intent_code",
                "lang_code",
                "utterance",
                "formality_level",
                "expected_entities",
                "notes",
            ),
            "normalization_rules": (
                "lang_code",
                "source_text",
                "normalized_text",
                "notes",
            ),
        }
        for table_name, columns in seed_tables.items():
            scoped_columns = ("client_id", "device_id", *columns)
            placeholders = ", ".join("?" for _ in scoped_columns)
            column_sql = ", ".join(scoped_columns)
            rows = DEFAULT_INTENT_SEED.get(table_name, [])
            if not rows:
                continue
            conn.executemany(
                f"""
                INSERT OR IGNORE INTO {table_name} ({column_sql})
                VALUES ({placeholders})
                """,
                [
                    (client_id, device_id, *(row.get(column) for column in columns))
                    for row in rows
                ],
            )

        for intent_code, item in DEFAULT_INTENT_MAPPINGS.items():
            if not isinstance(item, dict):
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO intent_mappings (
                    client_id,
                    device_id,
                    intent_code,
                    description,
                    required_slots,
                    optional_slots,
                    next_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    device_id,
                    str(intent_code),
                    item.get("description"),
                    json.dumps(item.get("required_slots") or [], ensure_ascii=True),
                    json.dumps(item.get("optional_slots") or [], ensure_ascii=True),
                    item.get("next_action"),
                ),
            )

    def _seed_internet_packages(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int,
        device_id: int,
    ) -> None:
        now = _utc_now()
        for item in DEFAULT_INTERNET_PACKAGES:
            conn.execute(
                """
                INSERT OR IGNORE INTO internet_packages (
                    client_id,
                    device_id,
                    package_code,
                    package_name,
                    speed_mbps,
                    monthly_price,
                    installation_fee,
                    installation_fee_label,
                    areas,
                    benefits,
                    is_active,
                    sort_order,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    device_id,
                    item["package_code"],
                    item["package_name"],
                    item["speed_mbps"],
                    item["monthly_price"],
                    item["installation_fee"],
                    item.get("installation_fee_label"),
                    json.dumps(item.get("areas") or [], ensure_ascii=True),
                    json.dumps(item.get("benefits") or [], ensure_ascii=True),
                    int(item.get("is_active", 1)),
                    item.get("sort_order", 100),
                    item.get("notes"),
                    now,
                    now,
                ),
            )

    def _seed_coverage_areas(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int,
        device_id: int,
    ) -> None:
        now = _utc_now()
        for item in DEFAULT_COVERAGE_AREAS:
            conn.execute(
                """
                INSERT OR IGNORE INTO coverage_areas (
                    client_id,
                    device_id,
                    area_code,
                    area_name,
                    city,
                    district,
                    coverage_status,
                    notes,
                    is_active,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    device_id,
                    item["area_code"],
                    item["area_name"],
                    item.get("city"),
                    item.get("district"),
                    item.get("coverage_status", "unknown"),
                    item.get("notes"),
                    int(item.get("is_active", 1)),
                    item.get("sort_order", 100),
                    now,
                    now,
                ),
            )

    def _seed_payment_methods(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int,
        device_id: int,
    ) -> None:
        now = _utc_now()
        for item in DEFAULT_PAYMENT_METHODS:
            conn.execute(
                """
                INSERT OR IGNORE INTO payment_methods (
                    client_id,
                    device_id,
                    method_code,
                    method_name,
                    is_available,
                    notes,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    device_id,
                    item["method_code"],
                    item["method_name"],
                    int(item.get("is_available", 1)),
                    item.get("notes"),
                    item.get("sort_order", 100),
                    now,
                    now,
                ),
            )

    def _seed_default_catalog_for_scope(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int,
        device_id: int,
    ) -> None:
        self._seed_intent_catalog(conn, client_id=client_id, device_id=device_id)
        self._seed_internet_packages(conn, client_id=client_id, device_id=device_id)
        self._seed_coverage_areas(conn, client_id=client_id, device_id=device_id)
        self._seed_payment_methods(conn, client_id=client_id, device_id=device_id)

    def _ensure_schema_migrations(self, conn: sqlite3.Connection) -> None:
        scoped_tables = (
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
        )
        for table_name in scoped_tables:
            self._ensure_column(conn, table_name, "client_id", "INTEGER")
            self._ensure_column(conn, table_name, "device_id", "INTEGER")

        self._ensure_column(conn, "conversation_states", "current_topic", "TEXT")
        self._ensure_column(conn, "conversation_states", "last_user_message", "TEXT")
        self._ensure_column(conn, "conversation_states", "last_bot_response", "TEXT")
        default_client_id, default_device_id = self._ensure_default_catalog_scope(conn)
        self._backfill_scope_columns(
            conn,
            default_client_id=default_client_id,
            default_device_id=default_device_id,
        )
        self._ensure_scope_indexes(conn)

    def _backfill_scope_columns(
        self,
        conn: sqlite3.Connection,
        *,
        default_client_id: int,
        default_device_id: int,
    ) -> None:
        for table_name in ("messages", "conversation_states", "conversation_logs"):
            conn.execute(
                f"""
                UPDATE {table_name}
                SET
                    client_id = COALESCE(
                        client_id,
                        (SELECT client_id FROM conversations WHERE conversations.id = {table_name}.conversation_id)
                    ),
                    device_id = COALESCE(
                        device_id,
                        (SELECT device_id FROM conversations WHERE conversations.id = {table_name}.conversation_id)
                    )
                WHERE client_id IS NULL OR device_id IS NULL
                """
            )

        conn.execute(
            """
            UPDATE unprocessed_questions
            SET
                client_id = COALESCE(
                    client_id,
                    (SELECT client_id FROM conversations WHERE conversations.id = unprocessed_questions.conversation_id)
                ),
                device_id = COALESCE(
                    device_id,
                    (SELECT device_id FROM conversations WHERE conversations.id = unprocessed_questions.conversation_id)
                )
            WHERE client_id IS NULL OR device_id IS NULL
            """
        )

        conn.execute(
            """
            UPDATE stock_products
            SET device_id = COALESCE(
                device_id,
                (
                    SELECT id
                    FROM devices
                    WHERE devices.client_id = stock_products.client_id
                    ORDER BY id
                    LIMIT 1
                ),
                ?
            )
            WHERE device_id IS NULL
            """,
            (default_device_id,),
        )

        default_scoped_tables = (
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
        )
        for table_name in default_scoped_tables:
            conn.execute(
                f"""
                UPDATE {table_name}
                SET
                    client_id = COALESCE(client_id, ?),
                    device_id = COALESCE(device_id, ?)
                WHERE client_id IS NULL OR device_id IS NULL
                """,
                (default_client_id, default_device_id),
            )

    def _ensure_scope_indexes(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_scope
                ON messages (client_id, device_id);
            CREATE INDEX IF NOT EXISTS idx_stock_products_scope
                ON stock_products (client_id, device_id);
            CREATE INDEX IF NOT EXISTS idx_internet_packages_scope_active_sort
                ON internet_packages (client_id, device_id, is_active, sort_order);
            CREATE INDEX IF NOT EXISTS idx_coverage_areas_scope_active_sort
                ON coverage_areas (client_id, device_id, is_active, sort_order);
            CREATE INDEX IF NOT EXISTS idx_payment_methods_scope_available_sort
                ON payment_methods (client_id, device_id, is_available, sort_order);
            CREATE INDEX IF NOT EXISTS idx_intents_scope_code
                ON intents (client_id, device_id, intent_code);
            CREATE INDEX IF NOT EXISTS idx_languages_scope_code
                ON languages (client_id, device_id, lang_code);
            CREATE INDEX IF NOT EXISTS idx_keywords_scope_intent_lang
                ON keywords (client_id, device_id, intent_code, lang_code);
            CREATE INDEX IF NOT EXISTS idx_entities_scope_code
                ON entities (client_id, device_id, entity_code);
            CREATE INDEX IF NOT EXISTS idx_entity_keywords_scope_entity_lang
                ON entity_keywords (client_id, device_id, entity_code, lang_code);
            CREATE INDEX IF NOT EXISTS idx_sample_utterances_scope_intent_lang
                ON sample_utterances (client_id, device_id, intent_code, lang_code);
            CREATE INDEX IF NOT EXISTS idx_normalization_rules_scope_lang
                ON normalization_rules (client_id, device_id, lang_code);
            CREATE INDEX IF NOT EXISTS idx_intent_mappings_scope_intent
                ON intent_mappings (client_id, device_id, intent_code);
            CREATE INDEX IF NOT EXISTS idx_unprocessed_questions_scope
                ON unprocessed_questions (client_id, device_id, status);
            CREATE INDEX IF NOT EXISTS idx_conversation_logs_scope
                ON conversation_logs (client_id, device_id, created_at);
            """
        )

    def _catalog_scope_for_table(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        *,
        client_id: int | None,
        device_id: int | None,
    ) -> tuple[int, int]:
        default_scope = self._ensure_default_catalog_scope(conn)
        if client_id is None or device_id is None:
            return default_scope

        scoped_row = conn.execute(
            f"""
            SELECT 1
            FROM {table_name}
            WHERE client_id = ? AND device_id = ?
            LIMIT 1
            """,
            (client_id, device_id),
        ).fetchone()
        if scoped_row:
            return client_id, device_id
        return default_scope

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.slug,
                    a.created_at,
                    a.updated_at,
                    COUNT(DISTINCT c.id) AS client_count,
                    COUNT(DISTINCT d.id) AS device_count
                FROM accounts a
                LEFT JOIN clients c ON c.account_id = a.id
                LEFT JOIN devices d ON d.client_id = c.id
                GROUP BY a.id
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_account(self, name: str, slug: str | None = None) -> dict[str, Any]:
        now = _utc_now()
        normalized_slug = _slugify(slug or name)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE slug = ?",
                (normalized_slug,),
            ).fetchone()
            if existing:
                raise ValueError(f"Account slug `{normalized_slug}` already exists.")

            cursor = conn.execute(
                """
                INSERT INTO accounts (name, slug, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip(), normalized_slug, now, now),
            )
            account_id = cursor.lastrowid
            row = conn.execute(
                """
                SELECT id, name, slug, created_at, updated_at
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()
        return dict(row) if row else {}

    def create_client(
        self,
        *,
        account_slug: str,
        name: str,
        external_ref: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        api_token = secrets.token_urlsafe(24)
        with self._connect() as conn:
            account = conn.execute(
                "SELECT id, name, slug FROM accounts WHERE slug = ?",
                (account_slug,),
            ).fetchone()
            if not account:
                raise ValueError(f"Account `{account_slug}` was not found.")

            cursor = conn.execute(
                """
                INSERT INTO clients (
                    account_id,
                    name,
                    external_ref,
                    api_token,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account["id"],
                    name.strip(),
                    external_ref.strip() if external_ref else None,
                    api_token,
                    now,
                    now,
                ),
            )
            client_id = cursor.lastrowid
            row = conn.execute(
                """
                SELECT
                    c.id,
                    c.account_id,
                    a.name AS account_name,
                    a.slug AS account_slug,
                    c.name,
                    c.external_ref,
                    c.api_token,
                    c.created_at,
                    c.updated_at
                FROM clients c
                JOIN accounts a ON a.id = c.account_id
                WHERE c.id = ?
                """,
                (client_id,),
            ).fetchone()
        return dict(row) if row else {}

    def list_clients(self, account_slug: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT
                c.id,
                c.account_id,
                a.name AS account_name,
                a.slug AS account_slug,
                c.name,
                c.external_ref,
                c.api_token,
                c.created_at,
                c.updated_at,
                COUNT(DISTINCT d.id) AS device_count,
                COUNT(DISTINCT conv.id) AS conversation_count
            FROM clients c
            JOIN accounts a ON a.id = c.account_id
            LEFT JOIN devices d ON d.client_id = c.id
            LEFT JOIN conversations conv ON conv.client_id = c.id
        """
        params: tuple[Any, ...] = ()
        if account_slug:
            query += " WHERE a.slug = ?"
            params = (account_slug,)
        query += " GROUP BY c.id ORDER BY c.created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def register_device(
        self,
        *,
        device_identifier: str,
        device_name: str | None,
        outbound_token: str | None,
        client_id: int | None = None,
        client_token: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            client = self._resolve_client(conn, client_id=client_id, client_token=client_token)
            if not client:
                raise ValueError("Client was not found for the provided identifier/token.")

            existing = conn.execute(
                "SELECT id FROM devices WHERE device_identifier = ?",
                (device_identifier,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE devices
                    SET client_id = ?, device_name = ?, outbound_token = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        client["id"],
                        device_name,
                        outbound_token,
                        now,
                        existing["id"],
                    ),
                )
                device_id = existing["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO devices (
                        client_id,
                        device_identifier,
                        device_name,
                        outbound_token,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client["id"],
                        device_identifier,
                        device_name,
                        outbound_token,
                        now,
                        now,
                    ),
                )
                device_id = cursor.lastrowid

            self._seed_default_catalog_for_scope(
                conn,
                client_id=int(client["id"]),
                device_id=int(device_id),
            )
            row = conn.execute(
                """
                SELECT
                    d.id,
                    d.device_identifier,
                    d.device_name,
                    d.outbound_token,
                    d.created_at,
                    d.updated_at,
                    c.id AS client_id,
                    c.name AS client_name,
                    c.api_token AS client_token,
                    a.slug AS account_slug
                FROM devices d
                JOIN clients c ON c.id = d.client_id
                JOIN accounts a ON a.id = c.account_id
                WHERE d.id = ?
                """,
                (device_id,),
            ).fetchone()
        return dict(row) if row else {}

    def save_incoming_message(self, payload: dict[str, Any]) -> StoredIncomingMessage:
        message_text = self._extract_message_text(payload)
        sender_number = self._extract_sender(payload)
        sender_name = self._extract_sender_name(payload)
        device_identifier = self._extract_device(payload)
        now = _utc_now()

        with self._connect() as conn:
            device = self._get_or_create_device_context(conn, device_identifier)
            conversation_id = self._get_or_create_conversation(
                conn=conn,
                client_id=device.client_id,
                device_id=device.device_id,
                sender_number=sender_number,
                sender_name=sender_name,
                at=now,
            )
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    client_id,
                    device_id,
                    conversation_id,
                    direction,
                    message_text,
                    raw_payload,
                    created_at
                )
                VALUES (?, ?, ?, 'incoming', ?, ?, ?)
                """,
                (
                    device.client_id,
                    device.device_id,
                    conversation_id,
                    message_text,
                    json.dumps(payload, ensure_ascii=True),
                    now,
                ),
            )

        return StoredIncomingMessage(
            conversation_id=conversation_id,
            message_id=int(cursor.lastrowid),
            sender_number=sender_number,
            sender_name=sender_name,
            message_text=message_text,
            device=device,
        )

    def save_outgoing_message(
        self,
        *,
        conversation_id: int,
        reply_text: str,
        matched_keywords: list[str],
        matched_product_names: list[str],
        raw_payload: dict[str, Any] | None = None,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            scope = self._get_conversation_scope(conn, conversation_id)
            conn.execute(
                """
                UPDATE conversations
                SET last_message_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, conversation_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    client_id,
                    device_id,
                    conversation_id,
                    direction,
                    message_text,
                    matched_keywords,
                    matched_product_name,
                    raw_payload,
                    created_at
                )
                VALUES (?, ?, ?, 'outgoing', ?, ?, ?, ?, ?)
                """,
                (
                    scope["client_id"],
                    scope["device_id"],
                    conversation_id,
                    reply_text,
                    json.dumps(matched_keywords, ensure_ascii=True),
                    json.dumps(matched_product_names, ensure_ascii=True),
                    json.dumps(raw_payload, ensure_ascii=True) if raw_payload else None,
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def update_incoming_message_analysis(
        self,
        *,
        message_id: int,
        matched_keywords: list[str],
        matched_product_names: list[str],
        reply_text: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE messages
                SET matched_keywords = ?, matched_product_name = ?, reply_text = ?
                WHERE id = ?
                """,
                (
                    json.dumps(matched_keywords, ensure_ascii=True),
                    json.dumps(matched_product_names, ensure_ascii=True),
                    reply_text,
                    message_id,
                ),
            )

    def get_conversation_state(self, conversation_id: int) -> dict[str, Any] | None:
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    conversation_id,
                    client_id,
                    device_id,
                    current_intent,
                    current_topic,
                    stage,
                    waiting_for,
                    collected_slots,
                    last_bot_question,
                    last_user_message,
                    last_bot_response,
                    next_action,
                    expires_at,
                    created_at,
                    updated_at
                FROM conversation_states
                WHERE conversation_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (conversation_id, now),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["waiting_for"] = self._decode_json_value(item.get("waiting_for"), [])
        item["collected_slots"] = self._decode_json_value(item.get("collected_slots"), {})
        return item

    def upsert_conversation_state(
        self,
        *,
        conversation_id: int,
        state: dict[str, Any] | None,
    ) -> None:
        if not state:
            return

        waiting_for = state.get("waiting_for") or []
        collected_slots = state.get("collected_slots") or {}
        stage = str(state.get("stage") or ("collecting_slots" if waiting_for else "ready"))
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        expires_at = (now_dt + timedelta(hours=self.settings.conversation_state_ttl_hours)).isoformat()
        with self._connect() as conn:
            scope = self._get_conversation_scope(conn, conversation_id)
            conn.execute(
                """
                INSERT INTO conversation_states (
                    conversation_id,
                    client_id,
                    device_id,
                    current_intent,
                    current_topic,
                    stage,
                    waiting_for,
                    collected_slots,
                    last_bot_question,
                    last_user_message,
                    last_bot_response,
                    next_action,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    client_id = excluded.client_id,
                    device_id = excluded.device_id,
                    current_intent = excluded.current_intent,
                    current_topic = excluded.current_topic,
                    stage = excluded.stage,
                    waiting_for = excluded.waiting_for,
                    collected_slots = excluded.collected_slots,
                    last_bot_question = excluded.last_bot_question,
                    last_user_message = excluded.last_user_message,
                    last_bot_response = excluded.last_bot_response,
                    next_action = excluded.next_action,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    conversation_id,
                    scope["client_id"],
                    scope["device_id"],
                    state.get("current_intent"),
                    state.get("current_topic"),
                    stage,
                    json.dumps(waiting_for, ensure_ascii=True),
                    json.dumps(collected_slots, ensure_ascii=True),
                    state.get("last_bot_question"),
                    state.get("last_user_message"),
                    state.get("last_bot_response"),
                    state.get("next_action"),
                    expires_at,
                    now,
                    now,
                ),
            )

    def get_intent_agent_catalog(
        self,
        *,
        client_id: int | None = None,
        device_id: int | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            intent_scope = self._catalog_scope_for_table(
                conn,
                "intents",
                client_id=client_id,
                device_id=device_id,
            )
            keyword_scope = self._catalog_scope_for_table(
                conn,
                "keywords",
                client_id=client_id,
                device_id=device_id,
            )
            entity_keyword_scope = self._catalog_scope_for_table(
                conn,
                "entity_keywords",
                client_id=client_id,
                device_id=device_id,
            )
            normalization_scope = self._catalog_scope_for_table(
                conn,
                "normalization_rules",
                client_id=client_id,
                device_id=device_id,
            )
            sample_scope = self._catalog_scope_for_table(
                conn,
                "sample_utterances",
                client_id=client_id,
                device_id=device_id,
            )
            mapping_scope = self._catalog_scope_for_table(
                conn,
                "intent_mappings",
                client_id=client_id,
                device_id=device_id,
            )
            package_scope = self._catalog_scope_for_table(
                conn,
                "internet_packages",
                client_id=client_id,
                device_id=device_id,
            )
            coverage_scope = self._catalog_scope_for_table(
                conn,
                "coverage_areas",
                client_id=client_id,
                device_id=device_id,
            )
            payment_scope = self._catalog_scope_for_table(
                conn,
                "payment_methods",
                client_id=client_id,
                device_id=device_id,
            )
            intents = conn.execute(
                """
                SELECT intent_code, intent_name, description
                FROM intents
                WHERE client_id = ? AND device_id = ?
                ORDER BY intent_code
                """,
                intent_scope,
            ).fetchall()
            intent_keywords = conn.execute(
                """
                SELECT
                    k.intent_code,
                    COALESCE(i.intent_name, k.intent_code) AS intent_name,
                    k.lang_code,
                    k.keyword,
                    k.normalized_keyword,
                    k.formality_level,
                    k.weight,
                    k.notes
                FROM keywords k
                LEFT JOIN intents i
                  ON i.intent_code = k.intent_code
                 AND i.client_id = k.client_id
                 AND i.device_id = k.device_id
                WHERE k.client_id = ? AND k.device_id = ?
                ORDER BY k.weight DESC, k.intent_code, k.lang_code, k.keyword
                """,
                keyword_scope,
            ).fetchall()
            entity_keywords = conn.execute(
                """
                SELECT
                    ek.entity_code,
                    COALESCE(e.entity_name, ek.entity_code) AS entity_name,
                    ek.lang_code,
                    ek.keyword,
                    ek.normalized_keyword,
                    ek.notes
                FROM entity_keywords ek
                LEFT JOIN entities e
                  ON e.entity_code = ek.entity_code
                 AND e.client_id = ek.client_id
                 AND e.device_id = ek.device_id
                WHERE ek.client_id = ? AND ek.device_id = ?
                ORDER BY ek.entity_code, ek.lang_code, ek.keyword
                """,
                entity_keyword_scope,
            ).fetchall()
            normalization_rules = conn.execute(
                """
                SELECT lang_code, source_text, normalized_text, notes
                FROM normalization_rules
                WHERE client_id = ? AND device_id = ?
                ORDER BY lang_code, source_text
                """,
                normalization_scope,
            ).fetchall()
            sample_utterances = conn.execute(
                """
                SELECT
                    intent_code,
                    lang_code,
                    utterance,
                    formality_level,
                    expected_entities,
                    notes
                FROM sample_utterances
                WHERE client_id = ? AND device_id = ?
                ORDER BY intent_code, lang_code, utterance
                """,
                sample_scope,
            ).fetchall()
            mappings = conn.execute(
                """
                SELECT
                    intent_code,
                    description,
                    required_slots,
                    optional_slots,
                    next_action
                FROM intent_mappings
                WHERE client_id = ? AND device_id = ?
                ORDER BY intent_code
                """,
                mapping_scope,
            ).fetchall()
            internet_packages = conn.execute(
                """
                SELECT
                    client_id,
                    device_id,
                    package_code,
                    package_name,
                    speed_mbps,
                    monthly_price,
                    installation_fee,
                    installation_fee_label,
                    areas,
                    benefits,
                    is_active,
                    sort_order,
                    notes
                FROM internet_packages
                WHERE client_id = ? AND device_id = ? AND is_active = 1
                ORDER BY sort_order, speed_mbps, package_name
                """,
                package_scope,
            ).fetchall()
            coverage_areas = conn.execute(
                """
                SELECT
                    client_id,
                    device_id,
                    area_code,
                    area_name,
                    city,
                    district,
                    coverage_status,
                    notes,
                    is_active,
                    sort_order
                FROM coverage_areas
                WHERE client_id = ? AND device_id = ? AND is_active = 1
                ORDER BY sort_order, area_name
                """,
                coverage_scope,
            ).fetchall()
            payment_methods = conn.execute(
                """
                SELECT
                    client_id,
                    device_id,
                    method_code,
                    method_name,
                    is_available,
                    notes,
                    sort_order
                FROM payment_methods
                WHERE client_id = ? AND device_id = ?
                ORDER BY sort_order, method_name
                """,
                payment_scope,
            ).fetchall()

        return {
            "intents": [dict(row) for row in intents],
            "intent_keywords": [dict(row) for row in intent_keywords],
            "entity_keywords": [dict(row) for row in entity_keywords],
            "normalization_rules": [dict(row) for row in normalization_rules],
            "sample_utterances": [dict(row) for row in sample_utterances],
            "intent_mappings": [dict(row) for row in mappings],
            "internet_packages": [
                self._decode_internet_package_row(dict(row))
                for row in internet_packages
            ],
            "coverage_areas": [dict(row) for row in coverage_areas],
            "payment_methods": [dict(row) for row in payment_methods],
        }

    def list_intents_for_mapping(
        self,
        *,
        client_id: int | None = None,
        device_id: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            intent_scope = self._catalog_scope_for_table(
                conn,
                "intents",
                client_id=client_id,
                device_id=device_id,
            )
            rows = conn.execute(
                """
                SELECT
                    i.intent_code,
                    i.intent_name,
                    i.description,
                    im.next_action,
                    im.required_slots,
                    im.optional_slots
                FROM intents i
                LEFT JOIN intent_mappings im
                  ON im.intent_code = i.intent_code
                 AND im.client_id = i.client_id
                 AND im.device_id = i.device_id
                WHERE i.intent_code != 'unknown'
                  AND i.client_id = ?
                  AND i.device_id = ?
                ORDER BY i.intent_code
                """,
                intent_scope,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_internet_packages(
        self,
        active_only: bool = True,
        *,
        client_id: int | None = None,
        client_token: str | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
    ) -> list[dict[str, Any]]:
        where_clause = "WHERE is_active = 1" if active_only else ""
        with self._connect() as conn:
            resolved_client = self._resolve_client(
                conn,
                client_id=client_id,
                client_token=client_token,
            )
            if client_id is not None or client_token:
                if not resolved_client:
                    raise ValueError("Client was not found for the provided identifier/token.")
                if device_id is None and not device_identifier:
                    raise ValueError("Provide `device_id` or `device_identifier` for client-scoped packages.")
            resolved_device = self._resolve_device(
                conn,
                client_id=int(resolved_client["id"]) if resolved_client else None,
                device_id=device_id,
                device_identifier=device_identifier,
            )
            if device_id is not None or device_identifier:
                if not resolved_device:
                    raise ValueError("Device was not found for the provided identifier.")
            scope_client_id = int(resolved_client["id"]) if resolved_client else None
            scope_device_id = int(resolved_device["id"]) if resolved_device else None
            package_scope = self._catalog_scope_for_table(
                conn,
                "internet_packages",
                client_id=scope_client_id,
                device_id=scope_device_id,
            )
            scoped_where = "client_id = ? AND device_id = ?"
            where_clause = (
                f"WHERE {scoped_where} AND is_active = 1"
                if active_only
                else f"WHERE {scoped_where}"
            )
            rows = conn.execute(
                f"""
                SELECT
                    id,
                    client_id,
                    device_id,
                    package_code,
                    package_name,
                    speed_mbps,
                    monthly_price,
                    installation_fee,
                    installation_fee_label,
                    areas,
                    benefits,
                    is_active,
                    sort_order,
                    notes,
                    created_at,
                    updated_at
                FROM internet_packages
                {where_clause}
                ORDER BY sort_order, speed_mbps, package_name
                """,
                package_scope,
            ).fetchall()
        return [self._decode_internet_package_row(dict(row)) for row in rows]

    def save_conversation_log(
        self,
        *,
        conversation_id: int,
        message_id: int | None,
        phone_number: str,
        user_message: str,
        detected_intent: str | None,
        confidence: float | None,
        entities: list[dict[str, Any]],
        state_before: dict[str, Any] | None,
        state_after: dict[str, Any] | None,
        knowledge: dict[str, Any] | None,
        bot_response: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            scope = self._get_conversation_scope(conn, conversation_id)
            conn.execute(
                """
                INSERT INTO conversation_logs (
                    client_id,
                    device_id,
                    conversation_id,
                    message_id,
                    phone_number,
                    user_message,
                    detected_intent,
                    confidence,
                    entities_json,
                    state_before_json,
                    state_after_json,
                    knowledge_json,
                    bot_response,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope["client_id"],
                    scope["device_id"],
                    conversation_id,
                    message_id,
                    phone_number,
                    user_message,
                    detected_intent,
                    confidence,
                    json.dumps(entities, ensure_ascii=True),
                    json.dumps(state_before or {}, ensure_ascii=True),
                    json.dumps(state_after or {}, ensure_ascii=True),
                    json.dumps(knowledge or {}, ensure_ascii=True),
                    bot_response,
                    now,
                ),
            )

    def save_unprocessed_question(
        self,
        *,
        stored_message: StoredIncomingMessage,
        analysis: dict[str, Any],
        reason: str,
    ) -> None:
        now = _utc_now()
        intent = analysis.get("intent") or {}
        normalized_text = _normalize_search_text(stored_message.message_text)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO unprocessed_questions (
                    client_id,
                    device_id,
                    conversation_id,
                    message_id,
                    language,
                    message_text,
                    normalized_text,
                    detected_intent_code,
                    confidence,
                    reason,
                    candidates,
                    entities,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    client_id = excluded.client_id,
                    device_id = excluded.device_id,
                    language = excluded.language,
                    message_text = excluded.message_text,
                    normalized_text = excluded.normalized_text,
                    detected_intent_code = excluded.detected_intent_code,
                    confidence = excluded.confidence,
                    reason = excluded.reason,
                    candidates = excluded.candidates,
                    entities = excluded.entities,
                    updated_at = excluded.updated_at
                """,
                (
                    stored_message.device.client_id,
                    stored_message.device.device_id,
                    stored_message.conversation_id,
                    stored_message.message_id,
                    str(analysis.get("language") or "id"),
                    stored_message.message_text,
                    normalized_text,
                    intent.get("intent_code"),
                    float(intent.get("confidence") or 0),
                    reason,
                    json.dumps(analysis.get("candidates") or [], ensure_ascii=True),
                    json.dumps(analysis.get("entities") or [], ensure_ascii=True),
                    now,
                    now,
                ),
            )

    def list_unprocessed_questions(
        self,
        *,
        status_filter: str = "pending",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        valid_statuses = {"pending", "mapped", "ignored", "all"}
        if status_filter not in valid_statuses:
            raise ValueError("Invalid status filter.")

        where_clause = ""
        params: list[Any] = []
        if status_filter != "all":
            where_clause = "WHERE uq.status = ?"
            params.append(status_filter)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    uq.id,
                    uq.client_id,
                    c.name AS client_name,
                    a.slug AS account_slug,
                    uq.device_id,
                    uq.conversation_id,
                    uq.message_id,
                    conv.sender_number,
                    conv.sender_name,
                    d.device_identifier,
                    uq.language,
                    uq.message_text,
                    uq.normalized_text,
                    uq.detected_intent_code,
                    uq.confidence,
                    uq.reason,
                    uq.candidates,
                    uq.entities,
                    uq.status,
                    uq.mapped_intent_code,
                    uq.mapped_type,
                    uq.reviewer_notes,
                    uq.created_at,
                    uq.updated_at,
                    uq.resolved_at
                FROM unprocessed_questions uq
                JOIN clients c ON c.id = uq.client_id
                JOIN accounts a ON a.id = c.account_id
                JOIN conversations conv ON conv.id = uq.conversation_id
                JOIN devices d ON d.id = uq.device_id
                {where_clause}
                ORDER BY uq.created_at DESC, uq.id DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()
        return [self._decode_unprocessed_question_row(dict(row)) for row in rows]

    def get_unprocessed_question(self, question_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            item = self._get_unprocessed_question(conn, question_id)
        if not item:
            raise ValueError("Unprocessed question was not found.")
        return item

    def map_unprocessed_question(
        self,
        *,
        question_id: int,
        intent_code: str | None,
        mapping_type: str,
        keyword: str | None = None,
        normalized_keyword: str | None = None,
        weight: int = 4,
        notes: str | None = None,
    ) -> dict[str, Any]:
        mapping_type = mapping_type.strip().lower()
        if mapping_type not in {"sample", "keyword", "both", "ignore"}:
            raise ValueError("mapping_type must be sample, keyword, both, or ignore.")

        safe_weight = max(1, min(weight, 10))
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, client_id, device_id, language, message_text, status
                FROM unprocessed_questions
                WHERE id = ?
                """,
                (question_id,),
            ).fetchone()
            if not row:
                raise ValueError("Unprocessed question was not found.")

            if mapping_type == "ignore":
                conn.execute(
                    """
                    UPDATE unprocessed_questions
                    SET
                        status = 'ignored',
                        mapped_intent_code = NULL,
                        mapped_type = ?,
                        reviewer_notes = ?,
                        updated_at = ?,
                        resolved_at = ?
                    WHERE id = ?
                    """,
                    (mapping_type, notes, now, now, question_id),
                )
                return self._get_unprocessed_question(conn, question_id)

            if not intent_code:
                raise ValueError("intent_code is required for mapped questions.")

            self._seed_intent_catalog(
                conn,
                client_id=int(row["client_id"]),
                device_id=int(row["device_id"]),
            )
            intent = conn.execute(
                """
                SELECT intent_code
                FROM intents
                WHERE intent_code = ? AND client_id = ? AND device_id = ?
                """,
                (intent_code, row["client_id"], row["device_id"]),
            ).fetchone()
            if not intent:
                raise ValueError(f"Intent `{intent_code}` was not found.")

            lang_code = str(row["language"] or "id")
            message_text = str(row["message_text"]).strip()
            mapping_notes = notes or f"Learned from unprocessed question #{question_id}."

            if mapping_type in {"sample", "both"}:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sample_utterances (
                        client_id,
                        device_id,
                        intent_code,
                        lang_code,
                        utterance,
                        formality_level,
                        expected_entities,
                        notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["client_id"],
                        row["device_id"],
                        intent_code,
                        lang_code,
                        message_text,
                        "learned",
                        "{}",
                        mapping_notes,
                    ),
                )

            if mapping_type in {"keyword", "both"}:
                keyword_text = (keyword or message_text).strip()
                normalized_text = (normalized_keyword or _normalize_search_text(keyword_text)).strip()
                if not keyword_text:
                    raise ValueError("keyword cannot be empty.")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO keywords (
                        client_id,
                        device_id,
                        intent_code,
                        lang_code,
                        keyword,
                        normalized_keyword,
                        formality_level,
                        weight,
                        notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["client_id"],
                        row["device_id"],
                        intent_code,
                        lang_code,
                        keyword_text,
                        normalized_text,
                        "learned",
                        safe_weight,
                        mapping_notes,
                    ),
                )

            conn.execute(
                """
                UPDATE unprocessed_questions
                SET
                    status = 'mapped',
                    mapped_intent_code = ?,
                    mapped_type = ?,
                    reviewer_notes = ?,
                    updated_at = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (intent_code, mapping_type, notes, now, now, question_id),
            )
            return self._get_unprocessed_question(conn, question_id)

    def _get_unprocessed_question(
        self,
        conn: sqlite3.Connection,
        question_id: int,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                uq.id,
                uq.client_id,
                c.name AS client_name,
                a.slug AS account_slug,
                uq.device_id,
                uq.conversation_id,
                uq.message_id,
                conv.sender_number,
                conv.sender_name,
                d.device_identifier,
                uq.language,
                uq.message_text,
                uq.normalized_text,
                uq.detected_intent_code,
                uq.confidence,
                uq.reason,
                uq.candidates,
                uq.entities,
                uq.status,
                uq.mapped_intent_code,
                uq.mapped_type,
                uq.reviewer_notes,
                uq.created_at,
                uq.updated_at,
                uq.resolved_at
            FROM unprocessed_questions uq
            JOIN clients c ON c.id = uq.client_id
            JOIN accounts a ON a.id = c.account_id
            JOIN conversations conv ON conv.id = uq.conversation_id
            JOIN devices d ON d.id = uq.device_id
            WHERE uq.id = ?
            """,
            (question_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unprocessed question was not found.")
        return self._decode_unprocessed_question_row(dict(row))

    def _decode_unprocessed_question_row(self, row: dict[str, Any]) -> dict[str, Any]:
        for key in ("candidates", "entities"):
            value = row.get(key)
            if not value:
                row[key] = []
                continue
            try:
                decoded = json.loads(str(value))
            except json.JSONDecodeError:
                decoded = []
            row[key] = decoded if isinstance(decoded, list) else []
        return row

    def list_stock_products(
        self,
        *,
        client_id: int | None = None,
        client_token: str | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        filters = []
        params: list[Any] = []

        with self._connect() as conn:
            resolved_client = self._resolve_client(
                conn,
                client_id=client_id,
                client_token=client_token,
            )
            if client_id is not None or client_token:
                if not resolved_client:
                    raise ValueError("Client was not found for the provided identifier/token.")
                filters.append("sp.client_id = ?")
                params.append(resolved_client["id"])

            resolved_device = self._resolve_device(
                conn,
                client_id=int(resolved_client["id"]) if resolved_client else None,
                device_id=device_id,
                device_identifier=device_identifier,
            )
            if device_id is not None or device_identifier:
                if not resolved_device:
                    raise ValueError("Device was not found for the provided identifier.")
                filters.append("sp.device_id = ?")
                params.append(resolved_device["id"])

            if query and query.strip():
                filters.append("LOWER(sp.product_name) LIKE ?")
                params.append(f"%{query.strip().lower()}%")

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            rows = conn.execute(
                f"""
                SELECT
                    sp.id,
                    sp.client_id,
                    sp.device_id,
                    c.name AS client_name,
                    a.slug AS account_slug,
                    d.device_identifier,
                    d.device_name,
                    sp.product_name,
                    sp.product_type,
                    sp.stock,
                    sp.metadata,
                    sp.created_at,
                    sp.updated_at
                FROM stock_products sp
                JOIN clients c ON c.id = sp.client_id
                JOIN accounts a ON a.id = c.account_id
                JOIN devices d ON d.id = sp.device_id
                {where_clause}
                ORDER BY sp.updated_at DESC, sp.id DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_stock_product(
        self,
        *,
        product_name: str,
        stock: int,
        product_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_id: int | None = None,
        client_token: str | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
    ) -> dict[str, Any]:
        normalized_name = product_name.strip()
        normalized_type = product_type.strip() if product_type else ""
        if not normalized_name:
            raise ValueError("Product name cannot be empty.")
        if stock < 0:
            raise ValueError("Stock cannot be negative.")

        now = _utc_now()
        with self._connect() as conn:
            client = self._resolve_client(conn, client_id=client_id, client_token=client_token)
            if not client:
                raise ValueError("Client was not found for the provided identifier/token.")
            device = self._resolve_device(
                conn,
                client_id=int(client["id"]),
                device_id=device_id,
                device_identifier=device_identifier,
            )
            if not device:
                raise ValueError("Device was not found for the provided identifier.")

            existing = conn.execute(
                """
                SELECT id
                FROM stock_products
                WHERE client_id = ? AND device_id = ? AND product_name = ? AND product_type = ?
                """,
                (client["id"], device["id"], normalized_name, normalized_type),
            ).fetchone()
            if existing:
                product_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE stock_products
                    SET stock = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        stock,
                        json.dumps(metadata, ensure_ascii=True) if metadata else None,
                        now,
                        product_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO stock_products (
                        client_id,
                        device_id,
                        product_name,
                        product_type,
                        stock,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client["id"],
                        device["id"],
                        normalized_name,
                        normalized_type,
                        stock,
                        json.dumps(metadata, ensure_ascii=True) if metadata else None,
                        now,
                        now,
                    ),
                )
                product_id = int(cursor.lastrowid)

            row = conn.execute(
                """
                SELECT
                    sp.id,
                    sp.client_id,
                    sp.device_id,
                    c.name AS client_name,
                    a.slug AS account_slug,
                    d.device_identifier,
                    d.device_name,
                    sp.product_name,
                    sp.product_type,
                    sp.stock,
                    sp.metadata,
                    sp.created_at,
                    sp.updated_at
                FROM stock_products sp
                JOIN clients c ON c.id = sp.client_id
                JOIN accounts a ON a.id = c.account_id
                JOIN devices d ON d.id = sp.device_id
                WHERE sp.id = ?
                """,
                (product_id,),
            ).fetchone()
        return dict(row) if row else {}

    def search_stock_products(
        self,
        *,
        client_id: int,
        device_id: int,
        query_tokens: list[str],
        limit: int = 5,
    ) -> list[StockMatch]:
        normalized_tokens = [
            _normalize_search_text(token)
            for token in query_tokens
            if token and token.strip()
        ]
        if not normalized_tokens:
            return []

        safe_limit = max(1, min(limit, 20))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, product_name, product_type, stock
                FROM stock_products
                WHERE client_id = ? AND device_id = ?
                """,
                (client_id, device_id),
            ).fetchall()

        ranked_rows: list[tuple[int, int, StockMatch]] = []
        for row in rows:
            product_name = str(row["product_name"])
            normalized_product = _normalize_search_text(product_name)
            score = sum(token in normalized_product for token in normalized_tokens)
            if score == 0:
                continue

            ranked_rows.append(
                (
                    score,
                    -len(product_name),
                    StockMatch(
                        product_id=int(row["id"]),
                        product_name=product_name,
                        product_type=str(row["product_type"] or ""),
                        stock=int(row["stock"] or 0),
                    ),
                )
            )

        ranked_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not ranked_rows:
            return []

        best_score = ranked_rows[0][0]
        return [match for score, _, match in ranked_rows if score == best_score][:safe_limit]

    def list_conversations(
        self,
        limit: int = 50,
        *,
        client_id: int | None = None,
        client_token: str | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        filters = []
        params: list[Any] = []
        with self._connect() as conn:
            resolved_client = self._resolve_client(
                conn,
                client_id=client_id,
                client_token=client_token,
            )
            if client_id is not None or client_token:
                if not resolved_client:
                    raise ValueError("Client was not found for the provided identifier/token.")
                filters.append("conv.client_id = ?")
                params.append(resolved_client["id"])

            resolved_device = self._resolve_device(
                conn,
                client_id=int(resolved_client["id"]) if resolved_client else None,
                device_id=device_id,
                device_identifier=device_identifier,
            )
            if device_id is not None or device_identifier:
                if not resolved_device:
                    raise ValueError("Device was not found for the provided identifier.")
                filters.append("conv.device_id = ?")
                params.append(resolved_device["id"])

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            rows = conn.execute(
                f"""
                SELECT
                    conv.id,
                    conv.sender_number,
                    conv.sender_name,
                    conv.last_message_at,
                    conv.created_at,
                    conv.updated_at,
                    c.id AS client_id,
                    c.name AS client_name,
                    c.api_token AS client_token,
                    a.slug AS account_slug,
                    d.id AS device_id,
                    d.device_identifier,
                    d.device_name,
                    (
                        SELECT m.message_text
                        FROM messages m
                        WHERE m.conversation_id = conv.id
                        ORDER BY m.created_at DESC, m.id DESC
                        LIMIT 1
                    ) AS last_message_text
                FROM conversations conv
                JOIN clients c ON c.id = conv.client_id
                JOIN accounts a ON a.id = c.account_id
                JOIN devices d ON d.id = conv.device_id
                {where_clause}
                ORDER BY conv.updated_at DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_messages(
        self,
        conversation_id: int,
        limit: int = 100,
        *,
        client_id: int | None = None,
        client_token: str | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            resolved_client = self._resolve_client(
                conn,
                client_id=client_id,
                client_token=client_token,
            )
            if client_id is not None or client_token:
                if not resolved_client:
                    raise ValueError("Client was not found for the provided identifier/token.")

            resolved_device = self._resolve_device(
                conn,
                client_id=int(resolved_client["id"]) if resolved_client else None,
                device_id=device_id,
                device_identifier=device_identifier,
            )
            if device_id is not None or device_identifier:
                if not resolved_device:
                    raise ValueError("Device was not found for the provided identifier.")

            conversation = conn.execute(
                """
                SELECT client_id, device_id
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if not conversation:
                raise ValueError("Conversation was not found.")
            if resolved_client and int(conversation["client_id"]) != int(resolved_client["id"]):
                raise ValueError("Conversation does not belong to the provided client.")
            if resolved_device and int(conversation["device_id"]) != int(resolved_device["id"]):
                raise ValueError("Conversation does not belong to the provided device.")

            rows = conn.execute(
                """
                SELECT
                    id,
                    client_id,
                    device_id,
                    conversation_id,
                    direction,
                    message_text,
                    matched_keywords,
                    matched_product_name,
                    reply_text,
                    raw_payload,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (conversation_id, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _decode_json_value(self, value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return fallback

    def _decode_internet_package_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["areas"] = self._decode_json_value(row.get("areas"), [])
        row["benefits"] = self._decode_json_value(row.get("benefits"), [])
        return row

    def _resolve_client(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int | None,
        client_token: str | None,
    ) -> sqlite3.Row | None:
        if client_id is not None:
            return conn.execute(
                "SELECT id, account_id, name, api_token FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
        if client_token:
            return conn.execute(
                "SELECT id, account_id, name, api_token FROM clients WHERE api_token = ?",
                (client_token,),
            ).fetchone()
        return None

    def _resolve_device(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int | None = None,
        device_id: int | None = None,
        device_identifier: str | None = None,
    ) -> sqlite3.Row | None:
        if device_id is not None:
            row = conn.execute(
                """
                SELECT id, client_id, device_identifier, device_name
                FROM devices
                WHERE id = ?
                """,
                (device_id,),
            ).fetchone()
        elif device_identifier:
            row = conn.execute(
                """
                SELECT id, client_id, device_identifier, device_name
                FROM devices
                WHERE device_identifier = ?
                """,
                (device_identifier,),
            ).fetchone()
        else:
            return None

        if not row:
            return None
        if client_id is not None and int(row["client_id"]) != client_id:
            return None
        return row

    def _get_conversation_scope(
        self,
        conn: sqlite3.Connection,
        conversation_id: int,
    ) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT client_id, device_id
            FROM conversations
            WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            raise ValueError("Conversation was not found.")
        return row

    def _get_or_create_device_context(
        self,
        conn: sqlite3.Connection,
        device_identifier: str,
    ) -> DeviceContext:
        row = conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.name AS account_name,
                a.slug AS account_slug,
                c.id AS client_id,
                c.name AS client_name,
                c.api_token AS client_token,
                d.id AS device_id,
                d.device_identifier,
                d.device_name,
                d.outbound_token
            FROM devices d
            JOIN clients c ON c.id = d.client_id
            JOIN accounts a ON a.id = c.account_id
            WHERE d.device_identifier = ?
            """,
            (device_identifier,),
        ).fetchone()
        if row:
            self._seed_default_catalog_for_scope(
                conn,
                client_id=int(row["client_id"]),
                device_id=int(row["device_id"]),
            )
            return DeviceContext(**dict(row))

        now = _utc_now()
        auto_account = conn.execute(
            "SELECT id, name, slug FROM accounts WHERE slug = ?",
            (self.settings.chat_auto_account_slug,),
        ).fetchone()
        if not auto_account:
            cursor = conn.execute(
                """
                INSERT INTO accounts (name, slug, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self.settings.chat_auto_account_name,
                    self.settings.chat_auto_account_slug,
                    now,
                    now,
                ),
            )
            auto_account = conn.execute(
                "SELECT id, name, slug FROM accounts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        client_name = f"Auto Client {device_identifier}"
        api_token = secrets.token_urlsafe(24)
        client_cursor = conn.execute(
            """
            INSERT INTO clients (
                account_id,
                name,
                external_ref,
                api_token,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                auto_account["id"],
                client_name,
                device_identifier,
                api_token,
                now,
                now,
            ),
        )
        client_id = int(client_cursor.lastrowid)
        device_cursor = conn.execute(
            """
            INSERT INTO devices (
                client_id,
                device_identifier,
                device_name,
                outbound_token,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                device_identifier,
                device_identifier,
                self.settings.fonnte_token or None,
                now,
                now,
            ),
        )
        self._seed_default_catalog_for_scope(
            conn,
            client_id=client_id,
            device_id=int(device_cursor.lastrowid),
        )
        return DeviceContext(
            account_id=int(auto_account["id"]),
            account_name=str(auto_account["name"]),
            account_slug=str(auto_account["slug"]),
            client_id=client_id,
            client_name=client_name,
            client_token=api_token,
            device_id=int(device_cursor.lastrowid),
            device_identifier=device_identifier,
            device_name=device_identifier,
            outbound_token=self.settings.fonnte_token or None,
        )

    def _get_or_create_conversation(
        self,
        *,
        conn: sqlite3.Connection,
        client_id: int,
        device_id: int,
        sender_number: str,
        sender_name: str | None,
        at: str,
    ) -> int:
        existing = conn.execute(
            """
            SELECT id
            FROM conversations
            WHERE client_id = ? AND device_id = ? AND sender_number = ?
            """,
            (client_id, device_id, sender_number),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE conversations
                SET sender_name = ?, last_message_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (sender_name, at, at, existing["id"]),
            )
            return int(existing["id"])

        cursor = conn.execute(
            """
            INSERT INTO conversations (
                client_id,
                device_id,
                sender_number,
                sender_name,
                last_message_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (client_id, device_id, sender_number, sender_name, at, at, at),
        )
        return int(cursor.lastrowid)

    def _extract_device(self, payload: dict[str, Any]) -> str:
        for key in ("device", "device_id", "deviceId"):
            value = payload.get(key)
            if value:
                return str(value)
        return "unknown-device"

    def _extract_sender(self, payload: dict[str, Any]) -> str:
        for key in ("sender", "from", "number", "phone"):
            value = payload.get(key)
            if value:
                return str(value)
        return "unknown-sender"

    def _extract_sender_name(self, payload: dict[str, Any]) -> str | None:
        for key in ("name", "sender_name", "pushName"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _extract_message_text(self, payload: dict[str, Any]) -> str:
        for key in ("message", "text", "body"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""
