from collections.abc import Mapping
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.template.loader import render_to_string

STORAGE_ALIAS = "documents"


class WeasyPdfRenderer:
    def render(self, template: str, context: Mapping[str, Any]) -> bytes:
        from weasyprint import HTML

        document: bytes = HTML(string=render_to_string(template, dict(context))).write_pdf()
        return document


class DjangoFileStore:
    def save(self, name: str, content: bytes) -> str:
        return str(storages[STORAGE_ALIAS].save(name, ContentFile(content)))

    def read(self, path: str) -> bytes:
        with storages[STORAGE_ALIAS].open(path, "rb") as handle:
            data: bytes = handle.read()
        return data

    def delete(self, path: str) -> None:
        storages[STORAGE_ALIAS].delete(path)
