from uuid import UUID

from apps.documents.domain.enums import JobKind, JobStatus
from core.events.base import DomainEvent, domain_event


@domain_event
class JobFinished(DomainEvent):
    job_id: UUID
    owner_id: int
    kind: JobKind
    status: JobStatus


@domain_event
class JobRequested(DomainEvent):
    job_id: UUID
