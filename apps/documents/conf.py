from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class DocumentSettings:
    max_export_rows: int = 20_000
    max_import_rows: int = 2_000
    max_import_bytes: int = 2_000_000
    retention_days: int = 7
    # personal data export: one request per hour (10 minutes after a failure), an export still
    # unfinished after 30 minutes counts as failed, download link valid 48 hours
    personal_data_cooldown_minutes: int = 60
    personal_data_failure_cooldown_minutes: int = 10
    personal_data_stale_minutes: int = 30
    personal_data_link_hours: int = 48
    personal_data_max_orders: int = 2_000
    personal_data_max_messages: int = 5_000
    company_name: str = "Celebobo"
    company_address: str = "Bukavu · Goma, RD Congo"
    company_contact: str = "contact@celebobo.cd"
    # the data-protection contact named by the privacy policy (§1), for personal data requests
    privacy_contact: str = "celestinbahiga@gmail.com"


def document_settings() -> DocumentSettings:
    return load_section("DOCUMENTS", DocumentSettings)
