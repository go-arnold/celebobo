from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

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

    def delete(self, job: Job) -> None:
        job.delete()
