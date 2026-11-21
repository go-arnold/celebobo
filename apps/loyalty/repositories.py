from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.loyalty.domain.points import CREDITS, EntryKind
from apps.loyalty.models import SETTINGS_ID, LoyaltySettings, PointsEntry


class LoyaltySettingsRepository:
    def current(self, *, for_update: bool = False) -> LoyaltySettings:
        settings = (
            LoyaltySettings.objects.select_for_update() if for_update else LoyaltySettings.objects
        )
        current, _ = settings.get_or_create(pk=SETTINGS_ID)
        return current

    def save(self, settings: LoyaltySettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])


class PointsRepository:
    # what the client can spend, oldest first; with `pending`, also what waits for the return period
    def credits(
        self, user_id: int, now: datetime, *, lock: bool = False, pending: bool = False
    ) -> list[PointsEntry]:
        rows = PointsEntry.objects.filter(
            user_id=user_id, kind__in=[kind.value for kind in CREDITS], remaining__gt=0
        )
        if not pending:
            rows = rows.filter(available_at__lte=now)
        rows = rows.order_by("available_at", "pk")
        return list(rows.select_for_update() if lock else rows)

    def recent(self, user_id: int, *, limit: int) -> list[PointsEntry]:
        return list(
            PointsEntry.objects.filter(user_id=user_id)
            .select_related("order")
            .order_by("-created_at", "-pk")[:limit]
        )

    def holders(self) -> list[int]:
        return list(
            PointsEntry.objects.filter(kind__in=[kind.value for kind in CREDITS], remaining__gt=0)
            .values_list("user_id", flat=True)
            .distinct()
        )

    def last_credit(self, user_id: int) -> datetime | None:
        return (
            PointsEntry.objects.filter(user_id=user_id, kind__in=[k.value for k in CREDITS])
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )

    def pending(self, user_id: int, now: datetime) -> Decimal:
        total = PointsEntry.objects.filter(
            user_id=user_id, kind=EntryKind.EARN.value, remaining__gt=0, available_at__gt=now
        ).aggregate(total=Sum("remaining"))["total"]
        return total or Decimal(0)

    def for_order(
        self, order_id: int, kind: EntryKind, *, lock: bool = False
    ) -> PointsEntry | None:
        rows = PointsEntry.objects.filter(order_id=order_id, kind=kind.value)
        return (rows.select_for_update() if lock else rows).first()

    def total_for_order(self, order_id: int, kind: EntryKind) -> Decimal:
        total = PointsEntry.objects.filter(order_id=order_id, kind=kind.value).aggregate(
            total=Sum("amount")
        )["total"]
        return total or Decimal(0)

    def add(self, **fields: Any) -> PointsEntry:
        entry: PointsEntry = PointsEntry.objects.create(**fields)
        return entry

    def use(self, entry: PointsEntry, remaining: Decimal) -> None:
        entry.remaining = remaining
        entry.save(update_fields=["remaining"])
