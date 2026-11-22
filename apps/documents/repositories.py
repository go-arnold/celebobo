from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Q

from apps.documents.domain.enums import JobKind, JobStatus
from apps.documents.models import Job


class JobRepository:
    def create(self, **fields: Any) -> Job:
        return Job.objects.create(**fields)

    def get(self, job_id: UUID, *, for_update: bool = False) -> Job | None:
        queryset = Job.objects.select_for_update() if for_update else Job.objects.all()
        return queryset.filter(pk=job_id).first()

    def save(self, job: Job, *, fields: Iterable[str]) -> None:
        job.save(update_fields=[*fields])

    def expired(self, before: datetime) -> list[Job]:
        return list(Job.objects.filter(created_at__lt=before))

    # finished (or stuck) before the cut-off
    def expired_of_kind(self, kind: JobKind, before: datetime) -> list[Job]:
        return list(
            Job.objects.filter(kind=kind.value).filter(
                Q(finished_at__lt=before) | Q(finished_at__isnull=True, created_at__lt=before)
            )
        )

    def latest(self, owner_id: int, kind: JobKind, *, include_failed: bool = True) -> Job | None:
        jobs = Job.objects.filter(owner_id=owner_id, kind=kind.value).defer("upload")
        if not include_failed:
            jobs = jobs.exclude(status=JobStatus.FAILED.value)
        return jobs.order_by("-created_at").first()

    def delete(self, job: Job) -> None:
        job.delete()
