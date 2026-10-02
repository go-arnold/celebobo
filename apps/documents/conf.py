from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class DocumentSettings:
    max_export_rows: int = 20_000
    max_import_rows: int = 2_000
    max_import_bytes: int = 2_000_000
    retention_days: int = 7
    company_name: str = "Celebobo"
    company_address: str = "Kinshasa, RD Congo"
    company_contact: str = "contact@celebobo.cd"


def document_settings() -> DocumentSettings:
    return load_section("DOCUMENTS", DocumentSettings)
