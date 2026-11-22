from collections.abc import Iterable
from typing import Any

from apps.warranty.domain.rules import OPEN_STATUSES, ClaimStatus, Outcome
from apps.warranty.models import Claim


class ClaimRepository:
    def create(self, **fields: Any) -> Claim:
        return Claim.objects.create(**fields)

    def get(self, claim_id: int, *, for_update: bool = False) -> Claim | None:
        queryset = Claim.objects.select_for_update() if for_update else Claim.objects
        return queryset.filter(pk=claim_id).first()

    def save(self, claim: Claim, *, fields: Iterable[str]) -> None:
        claim.save(update_fields=[*fields])

    def open_for_item(self, item_id: int) -> Claim | None:
        return Claim.objects.filter(
            item_id=item_id, status__in=[status.value for status in OPEN_STATUSES]
        ).first()

    # the days a unit of this line spent in repair: the warranty is extended by as much
    def repair_extension_days(self, item_id: int) -> int:
        rows = Claim.objects.filter(
            item_id=item_id,
            status=ClaimStatus.CLOSED.value,
            outcome=Outcome.REPAIR.value,
            received_at__isnull=False,
            repaired_at__isnull=False,
        ).values_list("received_at", "repaired_at")
        days = 0
        for received, repaired in rows:
            if received is not None and repaired is not None:
                days += (repaired.date() - received.date()).days
        return days
