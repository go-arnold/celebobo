from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from django.utils import timezone

from apps.documents.domain.enums import ALLOWED_FORMATS, JobFormat, JobKind, JobStatus
from apps.documents.domain.errors import (
    JobNotFound,
    PersonalDataExportTooSoon,
    UnsupportedFormat,
)
from apps.documents.models import Job
from apps.documents.repositories import JobRepository
from apps.documents.services.contracts import FileStore
from apps.documents.services.generators import JobRequest, generator_registry
from core.domain.actor import Actor, Role
from core.domain.errors import DomainError, Unauthenticated

ERROR_LIMIT = 500


class JobService:
    def __init__(
        self, jobs: JobRepository, store: FileStore, *, clock: Callable[[], datetime]
    ) -> None:
        self._jobs = jobs
        self._store = store
        self._clock = clock

    def request(
        self,
        actor: Actor,
        kind: JobKind,
        format: JobFormat,
        params: dict[str, Any],
        *,
        upload: bytes | None = None,
    ) -> Job:
        if format not in ALLOWED_FORMATS[kind]:
            raise UnsupportedFormat
        return self._jobs.create(
            owner_id=actor.user_id,
            kind=kind.value,
            format=format.value,
            params=params,
            upload=upload,
        )

    # one request per cooldown: a failed export does not count
    def request_personal_data(self, actor: Actor, *, cooldown: timedelta) -> Job:
        if actor.user_id is None:
            raise Unauthenticated
        available_at = self.personal_data_available_at(actor.user_id, cooldown=cooldown)
        if available_at is not None:
            raise PersonalDataExportTooSoon(timezone.localtime(available_at))
        return self.request(actor, JobKind.PERSONAL_DATA, JobFormat.ZIP, {})

    def personal_data_available_at(self, owner_id: int, *, cooldown: timedelta) -> datetime | None:
        last = self._jobs.latest(owner_id, JobKind.PERSONAL_DATA, include_failed=False)
        if last is None:
            return None
        available_at = last.created_at + cooldown
        return available_at if available_at > self._clock() else None

    def latest_personal_data(self, owner_id: int) -> Job | None:
        return self._jobs.latest(owner_id, JobKind.PERSONAL_DATA)

    # when the download link of a finished export stops working, and whether it already has
    def expiry(self, job: Job, *, ttl: timedelta) -> tuple[datetime | None, bool]:
        if job.finished_at is None or job.job_status is not JobStatus.DONE:
            return None, False
        expires_at = job.finished_at + ttl
        return expires_at, expires_at <= self._clock()

    def run(self, job_id: UUID) -> Job | None:
        job = self._jobs.get(job_id, for_update=True)
        if job is None or job.job_status is not JobStatus.PENDING:
            return None
        job.status = JobStatus.RUNNING.value
        self._jobs.save(job, fields=("status",))
        request = JobRequest(
            actor=Actor(role=Role(job.owner.role), user_id=job.owner_id),
            format=job.job_format,
            params=dict(job.params),
            upload=bytes(job.upload) if job.upload is not None else None,
        )
        try:
            output = generator_registry.create(job.kind).run(request)
        except DomainError as error:
            return self._fail(job, str(error.detail))
        if output.file is not None:
            job.file = self._store.save(f"{job.pk}/{output.file.filename}", output.file.content)
            job.filename = output.file.filename
            job.content_type = output.file.content_type
            job.size = len(output.file.content)
        job.summary = output.summary
        job.status = JobStatus.DONE.value
        job.upload = None
        job.finished_at = self._clock()
        self._jobs.save(
            job,
            fields=(
                "file",
                "filename",
                "content_type",
                "size",
                "summary",
                "status",
                "upload",
                "finished_at",
            ),
        )
        return job

    def fail(self, job_id: UUID, reason: str) -> Job | None:
        job = self._jobs.get(job_id, for_update=True)
        if job is None or job.job_status is JobStatus.DONE:
            return None
        return self._fail(job, reason)

    def owned(self, actor: Actor, job_id: UUID) -> Job:
        job = self._jobs.get(job_id)
        if job is None or job.owner_id != actor.user_id:
            raise JobNotFound
        return job

    def read(self, job: Job) -> bytes:
        return self._store.read(job.file)

    def purge(self, *, retention_days: int, personal_data_ttl: timedelta | None = None) -> int:
        now = self._clock()
        expired = {job.pk: job for job in self._jobs.expired(now - timedelta(days=retention_days))}
        if personal_data_ttl is not None:
            # personal data files go as soon as their link expires
            for job in self._jobs.expired_of_kind(JobKind.PERSONAL_DATA, now - personal_data_ttl):
                expired.setdefault(job.pk, job)
        for job in expired.values():
            if job.file:
                self._store.delete(job.file)
            self._jobs.delete(job)
        return len(expired)

    def _fail(self, job: Job, reason: str) -> Job:
        job.status = JobStatus.FAILED.value
        job.error = reason[:ERROR_LIMIT]
        job.upload = None
        job.finished_at = self._clock()
        self._jobs.save(job, fields=("status", "error", "upload", "finished_at"))
        return job
