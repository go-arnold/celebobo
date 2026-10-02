import csv
import io
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.documents.domain.tables import Table
from apps.documents.services.contracts import PdfRenderer, TabularWriter
from core.registry import Registry

writer_registry: Registry[TabularWriter] = Registry("document writer")


def cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return value


class CsvWriter:
    extension = "csv"
    content_type = "text/csv; charset=utf-8"

    def write(self, table: Table) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow([column.label for column in table.columns])
        writer.writerows([[_text(cell(value)) for value in row] for row in table.rows])
        return ("﻿" + buffer.getvalue()).encode()


class XlsxWriter:
    extension = "xlsx"
    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def write(self, table: Table) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = table.title[:31]
        sheet.append([column.label for column in table.columns])
        for header in sheet[1]:
            header.font = Font(bold=True)
        for row in table.rows:
            sheet.append([_number(cell(value)) for value in row])
        sheet.freeze_panes = "A2"
        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()


class PdfTableWriter:
    extension = "pdf"
    content_type = "application/pdf"

    def __init__(self, renderer: PdfRenderer, branding: Mapping[str, str]) -> None:
        self._renderer = renderer
        self._branding = branding

    def write(self, table: Table) -> bytes:
        return self._renderer.render(
            "documents/table.html",
            {
                "table": table,
                "rows": [[cell(value) for value in row] for row in table.rows],
                "generated_at": timezone.localtime(),
                **self._branding,
            },
        )


def _text(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def _number(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return _text(value)
