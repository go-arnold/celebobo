from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import connection
from django.db.models import Q

from apps.documents.domain.enums import JobKind, JobStatus
from apps.documents.models import Job

OWNER_LOCK = 7302  # advisory lock namespace for personal data export requests


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

    # failed: None for any status, True for failed jobs only, False for the others
    def latest(self, owner_id: int, kind: JobKind, *, failed: bool | None = None) -> Job | None:
        jobs = Job.objects.filter(owner_id=owner_id, kind=kind.value).defer("upload")
        if failed is True:
            jobs = jobs.filter(status=JobStatus.FAILED.value)
        elif failed is False:
            jobs = jobs.exclude(status=JobStatus.FAILED.value)
        return jobs.order_by("-created_at").first()

    # serialises an owner's requests until the transaction ends
    def lock_owner(self, owner_id: int) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [OWNER_LOCK, owner_id])

    # marks the owner's jobs still pending or running since before the cut-off as failed;
    # a job a worker holds right now is left alone
    def fail_lost(
        self, owner_id: int, kind: JobKind, *, created_before: datetime, reason: str, now: datetime
    ) -> int:
        lost = list(
            Job.objects.select_for_update(skip_locked=True)
            .filter(
                owner_id=owner_id,
                kind=kind.value,
                status__in=(JobStatus.PENDING.value, JobStatus.RUNNING.value),
                created_at__lt=created_before,
            )
            .values_list("pk", flat=True)
        )
        return Job.objects.filter(pk__in=lost).update(
            status=JobStatus.FAILED.value, error=reason, upload=None, finished_at=now
        )

    def delete(self, job: Job) -> None:
        job.delete()
