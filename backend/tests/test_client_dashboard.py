from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.core.config import Settings
from app.services.chat_store import SQLiteChatStore
from app.services.client_dashboard_auth import ClientDashboardTokenService


class ClientDashboardTests(unittest.TestCase):
    def _new_store(self, temp_dir: str, billing_sample_path: str = "") -> SQLiteChatStore:
        return SQLiteChatStore(
            Settings(
                chat_database_path=str(Path(temp_dir) / "chat.sqlite3"),
                billing_sample_xlsx_path=billing_sample_path,
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
