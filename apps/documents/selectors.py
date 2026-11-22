from collections.abc import Iterable

from apps.documents.domain.enums import JobKind
from apps.documents.domain.read_models import JobView, ReceiptRef
from apps.documents.models import DeliveryReceipt, Job


class JobSelector:
    # back-office exports and imports; personal data exports have their own screen
    def page(self, owner_id: int, *, offset: int, limit: int) -> tuple[list[JobView], int]:
        jobs = (
            Job.objects.filter(owner_id=owner_id)
            .exclude(kind=JobKind.PERSONAL_DATA.value)
            .defer("upload")
        )
        page = jobs.order_by("-created_at")[offset : offset + limit]
        return [to_job_view(job) for job in page], jobs.count()


class ReceiptSelector:
    def for_orders(self, order_ids: Iterable[int]) -> dict[int, ReceiptRef]:
        receipts = DeliveryReceipt.objects.filter(order_id__in=list(order_ids)).only(
            "order_id", "number", "issued_at"
        )
        return {
            receipt.order_id: ReceiptRef(number=receipt.number, issued_at=receipt.issued_at)
            for receipt in receipts
        }


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
