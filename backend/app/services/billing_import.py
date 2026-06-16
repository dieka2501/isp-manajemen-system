from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile


SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
EXCEL_EPOCH = date(1899, 12, 30)


def excel_serial_to_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return (EXCEL_EPOCH + timedelta(days=int(value))).isoformat()


def load_billing_rows(path: str | Path) -> list[dict[str, Any]]:
    workbook_path = Path(path)
    if not workbook_path.exists():
        return []

    with ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        sheet_xml = archive.read(sheet_path)

    root = ElementTree.fromstring(sheet_xml)
    rows: list[list[Any]] = []
    for row in root.findall(f".//{{{SPREADSHEET_NS}}}sheetData/{{{SPREADSHEET_NS}}}row"):
        values: dict[int, Any] = {}
        for cell in row.findall(f"{{{SPREADSHEET_NS}}}c"):
            ref = cell.attrib.get("r", "")
            col_index = _column_index(ref)
            if col_index < 0:
                continue
            values[col_index] = _cell_value(cell, shared_strings)
        if values:
            width = max(values) + 1
            rows.append([values.get(index) for index in range(width)])

    if not rows:
        return []

    headers = [str(value or "").strip() for value in rows[0]]
    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        record = {
            header: row[index] if index < len(row) else None
            for index, header in enumerate(headers)
            if header
        }
        if any(value not in (None, "") for value in record.values()):
            records.append(record)
    return records


def _read_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    for item in root.findall(f"{{{SPREADSHEET_NS}}}si"):
        fragments = [
            text.text or ""
            for text in item.findall(f".//{{{SPREADSHEET_NS}}}t")
        ]
        strings.append("".join(fragments))
    return strings


def _first_sheet_path(archive: ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib.get("Id"): rel.attrib.get("Target", "")
        for rel in rels.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    first_sheet = workbook.find(f".//{{{SPREADSHEET_NS}}}sheet")
    if first_sheet is None:
        raise ValueError("Workbook does not contain any sheets.")
    rel_id = first_sheet.attrib.get(f"{{{REL_NS}}}id")
    target = targets.get(rel_id)
    if not target:
        raise ValueError("Workbook sheet relationship is missing.")
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            text.text or ""
            for text in cell.findall(f".//{{{SPREADSHEET_NS}}}t")
        )

    value_node = cell.find(f"{{{SPREADSHEET_NS}}}v")
    if value_node is None or value_node.text is None:
        return None

    raw_value = value_node.text.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError):
            return raw_value
    if cell_type == "b":
        return raw_value == "1"
    return _parse_number(raw_value)


def _parse_number(value: str) -> Any:
    try:
        numeric = float(value)
    except ValueError:
        return value
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _column_index(cell_ref: str) -> int:
    letters = ""
    for char in cell_ref:
        if char.isalpha():
            letters += char.upper()
        else:
            break
    if not letters:
        return -1

    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1
