from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.documents.domain.enums import JobFormat, JobKind, JobStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class JobView:
    id: UUID
    kind: JobKind
    format: JobFormat
    status: JobStatus
    filename: str
    size: int
    summary: dict[str, Any]
    error: str
    created_at: datetime
    finished_at: datetime | None
    # personal data exports only: the download link stops working then
    expires_at: datetime | None = None
    expired: bool = False

    @property
    def downloadable(self) -> bool:
        return self.status is JobStatus.DONE and bool(self.filename) and not self.expired


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalDataStatus:
    """The owner's latest personal data export, and when they may ask for a new one."""

    job: JobView | None
    # None: a new export can be requested now
    available_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceiptRef:
    number: str
    issued_at: datetime
