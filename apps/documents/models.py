import uuid

from django.conf import settings
from django.db import models

from apps.documents.domain.enums import JobFormat, JobKind, JobStatus


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_jobs"
    )
    kind = models.CharField(max_length=24, choices=[(item.value, item.value) for item in JobKind])
    format = models.CharField(
        max_length=8, choices=[(item.value, item.value) for item in JobFormat]
    )
    status = models.CharField(
        max_length=8,
        choices=[(item.value, item.value) for item in JobStatus],
        default=JobStatus.PENDING.value,
        db_index=True,
    )
    params = models.JSONField(default=dict, blank=True)
    upload = models.BinaryField(null=True, blank=True)
    file = models.CharField(max_length=255, blank=True)
    filename = models.CharField(max_length=160, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "tâche documentaire"
        verbose_name_plural = "tâches documentaires"
        ordering = ("-created_at",)
        indexes = (models.Index(fields=("owner", "-created_at"), name="documents_job_owner"),)

    def __str__(self) -> str:
        return f"{self.kind} {self.format} ({self.status})"

    @property
    def job_kind(self) -> JobKind:
        return JobKind(self.kind)

    @property
    def job_format(self) -> JobFormat:
        return JobFormat(self.format)

    @property
    def job_status(self) -> JobStatus:
        return JobStatus(self.status)
