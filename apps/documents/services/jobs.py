from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from apps.documents.domain.enums import ALLOWED_FORMATS, JobFormat, JobKind, JobStatus
from apps.documents.domain.errors import JobNotFound, UnsupportedFormat
from apps.documents.models import Job
from apps.documents.repositories import JobRepository
from apps.documents.services.contracts import FileStore
from apps.documents.services.generators import JobRequest, generator_registry
from core.domain.actor import Actor, Role
from core.domain.errors import DomainError

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

    def purge(self, *, retention_days: int) -> int:
        expired = self._jobs.expired(self._clock() - timedelta(days=retention_days))
        for job in expired:
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
