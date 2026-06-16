from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core.config import Settings
from app.api.sqlite_explorer import _parse_multipart_form
from app.services.billing_import import load_billing_rows_from_bytes
from app.services.chat_store import SQLiteChatStore
from app.services.client_dashboard_auth import ClientDashboardTokenService
from app.services.sqlite_explorer import SQLiteExplorerService


class ClientDashboardTests(unittest.TestCase):
    def _new_store(self, temp_dir: str, billing_sample_path: str = "") -> SQLiteChatStore:
        return SQLiteChatStore(
            Settings(
                chat_database_path=str(Path(temp_dir) / "chat.sqlite3"),
                billing_sample_xlsx_path=billing_sample_path,
                client_dashboard_seed_email="admin@isp.local",
                client_dashboard_seed_password="password",
            )
        )

    def test_seed_client_can_login_with_hashed_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = self._new_store(temp_dir)
            store.initialize()

            client = store.authenticate_client(
                identifier="admin@isp.local",
                password="password",
            )
            with store._connect() as conn:
                row = conn.execute(
                    """
                    SELECT email, password_hash, office_address, pic_name
                    FROM clients
                    WHERE email = 'admin@isp.local'
                    """
                ).fetchone()

        self.assertIsNotNone(client)
        self.assertEqual(client["email"], "admin@isp.local")
        self.assertEqual(row["office_address"], "Kantor ISP")
        self.assertEqual(row["pic_name"], "Admin ISP")
        self.assertNotEqual(row["password_hash"], "password")
        self.assertTrue(str(row["password_hash"]).startswith("pbkdf2_sha256$"))

    def test_token_service_roundtrip_and_rejects_bad_token(self) -> None:
        service = ClientDashboardTokenService(
            Settings(client_dashboard_jwt_secret="unit-test-secret")
        )

        token, _ = service.issue_token(42)

        self.assertEqual(service.require_client_id(f"Bearer {token}"), 42)
        with self.assertRaises(HTTPException):
            service.require_client_id(f"Bearer {token}x")

    def test_sample_billing_workbook_seeds_customers_and_billing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "billing.xlsx"
            _write_minimal_billing_xlsx(workbook_path)
            store = self._new_store(temp_dir, str(workbook_path))

            store.initialize()
            client = store.authenticate_client(
                identifier="admin@isp.local",
                password="password",
            )
            customers = store.list_customers(client_id=client["id"])
            billing = store.list_billing_records(client_id=client["id"])
            packages = store.list_client_packages(client_id=client["id"])

        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0]["customer_code"], "ASM001")
        self.assertEqual(customers[0]["package_name"], "10Mbps")
        self.assertEqual(len(billing), 1)
        self.assertEqual(billing[0]["status"], "paid")
        self.assertEqual(billing[0]["amount"], 200000)
        self.assertIn("10Mbps", {package["package_name"] for package in packages})

    def test_manual_billing_import_from_uploaded_workbook_bytes_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "billing.xlsx"
            _write_minimal_billing_xlsx(workbook_path)
            store = self._new_store(temp_dir)

            store.initialize()
            client = store.authenticate_client(
                identifier="admin@isp.local",
                password="password",
            )
            rows = load_billing_rows_from_bytes(workbook_path.read_bytes())
            first_summary = store.import_billing_rows(
                rows=rows,
                client_id=client["id"],
            )
            second_summary = store.import_billing_rows(
                rows=rows,
                client_id=client["id"],
            )
            customers = store.list_customers(client_id=client["id"])
            billing = store.list_billing_records(client_id=client["id"])
            scopes = store.billing_import_scopes()

        self.assertEqual(first_summary["processed_rows"], 1)
        self.assertEqual(second_summary["processed_rows"], 1)
        self.assertEqual(len(customers), 1)
        self.assertEqual(len(billing), 1)
        self.assertEqual(scopes[0]["devices"][0]["client_id"], client["id"])

    def test_sqlite_explorer_multipart_parser_reads_billing_file_and_fields(self) -> None:
        boundary = "billing-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="client_id"\r\n\r\n'
            "7\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="billing_file"; filename="billing.xlsx"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
        ).encode("utf-8") + b"fake-xlsx-bytes\r\n" + f"--{boundary}--\r\n".encode("utf-8")

        fields, files = _parse_multipart_form(
            content_type=f"multipart/form-data; boundary={boundary}",
            body=body,
        )

        self.assertEqual(fields["client_id"], "7")
        self.assertEqual(files["billing_file"].filename, "billing.xlsx")
        self.assertEqual(files["billing_file"].data, b"fake-xlsx-bytes")

    def test_sqlite_explorer_allows_insert_and_update_statements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE notes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL)"
                )

            service = SQLiteExplorerService(Settings(chat_database_path=str(db_path)))
            insert_result = service.run_query(
                str(db_path),
                "INSERT INTO notes (name, status) VALUES ('Customer A', 'new');",
            )
            update_result = service.run_query(
                str(db_path),
                "UPDATE notes SET status = 'done' WHERE name = 'Customer A';",
            )
            select_result = service.run_query(
                str(db_path),
                "SELECT name, status FROM notes;",
                limit=10,
            )

        self.assertEqual(insert_result["operation"], "insert")
        self.assertEqual(insert_result["rows_affected"], 1)
        self.assertEqual(update_result["operation"], "update")
        self.assertEqual(update_result["rows_affected"], 1)
        self.assertEqual(select_result["rows"], [{"name": "Customer A", "status": "done"}])

    def test_sqlite_explorer_lists_tables_with_readonly_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE notes (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
                )

            service = SQLiteExplorerService(Settings(chat_database_path=str(db_path)))
            tables = service.list_tables(str(db_path))

        self.assertEqual(tables[0]["name"], "notes")
        self.assertEqual(tables[0]["row_count"], 0)
        self.assertEqual(tables[0]["columns"][0]["name"], "id")

    def test_sqlite_explorer_rejects_non_insert_update_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ops.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE notes (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
                )

            service = SQLiteExplorerService(Settings(chat_database_path=str(db_path)))
            with self.assertRaisesRegex(ValueError, "Only SELECT, PRAGMA, INSERT, and UPDATE"):
                service.run_query(str(db_path), "DELETE FROM notes;")


def _write_minimal_billing_xlsx(path: Path) -> None:
    headers = [
        "No",
        "Nama",
        "No HP",
        "Alamat Lengkap",
        "PPPOE",
        "Paket",
        "Pembayran",
        "Bayar",
        "Status",
        "Tanggal",
        "Japo",
        "Rekening",
        "Sistem Pembayaran",
    ]
    row = [
        1,
        "ASM001 Customer Test",
        "08123456789",
        "Jl. Testing",
        "test@pppoe",
        "10Mbps",
        200000,
        200000,
        "lunas",
        46152,
        "TGL 1 - 10",
        "BCA",
        "Prabayar",
    ]
    sheet_rows = [_xlsx_row(1, headers), _xlsx_row(2, row)]
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Lembar1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _xlsx_row(row_number: int, values: list[object]) -> str:
    cells = []
    for index, value in enumerate(values):
        ref = f"{chr(ord('A') + index)}{row_number}"
        if isinstance(value, (int, float)):
            cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        else:
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{_xml_escape(str(value))}</t></is></c>'
            )
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


if __name__ == "__main__":
    unittest.main()
