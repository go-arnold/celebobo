from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet

from apps.audit.domain.retention import Expired
from apps.resellers.domain.enums import ApplicationStatus
from apps.resellers.models import ResellerApplication


class ApplicationRepository:
    def create(self, **fields: Any) -> ResellerApplication:
        return ResellerApplication.objects.create(**fields)

    def get(self, application_id: int, *, for_update: bool = False) -> ResellerApplication | None:
        queryset = (
            ResellerApplication.objects.select_for_update()
            if for_update
            else ResellerApplication.objects.all()
        )
        return queryset.filter(pk=application_id).first()

    def pending_for(self, email: str) -> bool:
        return ResellerApplication.objects.filter(
            email__iexact=email, status=ApplicationStatus.PENDING.value
        ).exists()

    def save(self, application: ResellerApplication, *, fields: Iterable[str]) -> None:
        application.save(update_fields=[*fields])

    def rejected_before(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        rows = (
            _rejected_before(cutoff)
            .filter(pk__gt=after_id)
            .order_by("pk")
            .values_list("pk", "reviewed_at", "created_at")[:limit]
        )
        return [
            Expired(pk, f"candidature #{pk} refusée le {(reviewed or received):%Y-%m-%d}")
            for pk, reviewed, received in rows
        ]

    def delete_rejected(self, ids: list[int], *, before: datetime) -> int:
        _, deleted = _rejected_before(before).filter(pk__in=ids).delete()
        return deleted.get(ResellerApplication._meta.label, 0)


# the decision date, or the date it was received for rejections recorded without one
def _rejected_before(cutoff: datetime) -> QuerySet[ResellerApplication]:
    return ResellerApplication.objects.filter(
        Q(reviewed_at__lt=cutoff) | Q(reviewed_at__isnull=True, created_at__lt=cutoff),
        status=ApplicationStatus.REJECTED.value,
    )
