from dataclasses import dataclass
from datetime import date

from apps.audit.domain.enums import AuditAction


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeFilters:
    actor_id: int | None = None
    action: AuditAction | None = None
    object_type: str | None = None
    object_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EventFilters:
    event_type: str | None = None
    actor_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
