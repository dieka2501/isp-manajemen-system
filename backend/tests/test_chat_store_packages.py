from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore


class SQLitePackageCatalogTests(unittest.TestCase):
    def test_initialize_seeds_default_internet_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "chat.sqlite3")
            store = SQLiteChatStore(Settings(chat_database_path=db_path))

            store.initialize()
            packages = store.list_internet_packages()

        package_names = {package["package_name"] for package in packages}
        self.assertEqual(len(packages), 4)
        self.assertIn("Paket Hemat", package_names)
        self.assertIn("Paket Keluarga", package_names)
        self.assertIn("Paket Premium", package_names)
        self.assertIn("Paket Office", package_names)


if __name__ == "__main__":
    unittest.main()
