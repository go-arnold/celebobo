from apps.documents.domain.read_models import JobView
from apps.documents.models import Job


class JobSelector:
    def page(self, owner_id: int, *, offset: int, limit: int) -> tuple[list[JobView], int]:
        jobs = Job.objects.filter(owner_id=owner_id).defer("upload")
        page = jobs.order_by("-created_at")[offset : offset + limit]
        return [to_job_view(job) for job in page], jobs.count()


def to_job_view(job: Job) -> JobView:
    return JobView(
        id=job.pk,
        kind=job.job_kind,
        format=job.job_format,
        status=job.job_status,
        filename=job.filename,
        size=job.size,
        summary=dict(job.summary),
        error=job.error,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )
