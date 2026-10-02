from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class AuditSettings:
    retention_days: int = 365
    ignored_events: tuple[str, ...] = (
        "apps.analytics.domain.events.SalesFactsRefreshed",
        "apps.documents.domain.events.JobRequested",
    )


def audit_settings() -> AuditSettings:
    return load_section("AUDIT", AuditSettings)
