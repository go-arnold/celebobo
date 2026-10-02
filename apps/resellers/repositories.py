from collections.abc import Iterable
from typing import Any

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
