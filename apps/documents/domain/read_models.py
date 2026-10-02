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

    @property
    def downloadable(self) -> bool:
        return self.status is JobStatus.DONE and bool(self.filename)
