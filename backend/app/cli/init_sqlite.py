from __future__ import annotations

from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore


def main() -> None:
    settings = get_settings()
    SQLiteChatStore(settings).initialize()
    print(f"SQLite database initialized: {settings.chat_database_path}")


if __name__ == "__main__":
    main()
