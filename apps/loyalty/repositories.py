from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.loyalty.domain.cashback import CREDITS, EntryKind
from apps.loyalty.models import (
    SETTINGS_ID,
    CashbackEntry,
    LoyaltyRule,
    LoyaltySettings,
    PointTransaction,
)


class LoyaltySettingsRepository:
    def current(self, *, for_update: bool = False) -> LoyaltySettings:
        settings = (
            LoyaltySettings.objects.select_for_update() if for_update else LoyaltySettings.objects
        )
        current, _ = settings.get_or_create(pk=SETTINGS_ID)
        return current

    def save(self, settings: LoyaltySettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])


class LoyaltyRuleRepository:
    def all(self, *, is_active: bool | None = None) -> list[LoyaltyRule]:
        rows = LoyaltyRule.objects.all()
        if is_active is not None:
            rows = rows.filter(is_active=is_active)
        return list(rows.order_by("trigger", "name"))

    def get(self, rule_id: int) -> LoyaltyRule | None:
        return LoyaltyRule.objects.filter(pk=rule_id).first()

    def create(self, **fields: Any) -> LoyaltyRule:
        rule: LoyaltyRule = LoyaltyRule.objects.create(**fields)
        return rule

    def update(self, rule: LoyaltyRule, *, fields: Iterable[str]) -> None:
        rule.save(update_fields=[*fields, "updated_at"])

    def delete(self, rule: LoyaltyRule) -> None:
        rule.delete()


class PointTransactionRepository:
    def for_user(
        self, user_id: int, *, offset: int, limit: int
    ) -> tuple[list[PointTransaction], int]:
        rows = PointTransaction.objects.filter(user_id=user_id).order_by("-created_at", "-pk")
        total = rows.count()
        page = rows[offset : offset + limit]
        return list(page), total

    def add(self, **fields: Any) -> PointTransaction:
        entry: PointTransaction = PointTransaction.objects.create(**fields)
        return entry


class CashbackRepository:
    def credits(self, user_id: int, now: datetime, *, lock: bool = False) -> list[CashbackEntry]:
        rows = CashbackEntry.objects.filter(
            user_id=user_id,
            kind__in=[kind.value for kind in CREDITS],
            remaining__gt=0,
            available_at__lte=now,
            expires_at__gt=now,
        ).order_by("expires_at", "pk")
        return list(rows.select_for_update() if lock else rows)

    def pending(self, user_id: int, now: datetime) -> Decimal:
        total = CashbackEntry.objects.filter(
            user_id=user_id, kind=EntryKind.EARN.value, remaining__gt=0, available_at__gt=now
        ).aggregate(total=Sum("remaining"))["total"]
        return total or Decimal(0)

    def for_order(
        self, order_id: int, kind: EntryKind, *, lock: bool = False
    ) -> CashbackEntry | None:
        rows = CashbackEntry.objects.filter(order_id=order_id, kind=kind.value)
        return (rows.select_for_update() if lock else rows).first()

    def expired(self, now: datetime) -> list[CashbackEntry]:
        return list(
            CashbackEntry.objects.select_for_update().filter(
                kind__in=[kind.value for kind in CREDITS], remaining__gt=0, expires_at__lte=now
            )
        )

    def add(self, **fields: Any) -> CashbackEntry:
        entry: CashbackEntry = CashbackEntry.objects.create(**fields)
        return entry

    def use(self, entry: CashbackEntry, remaining: Decimal) -> None:
        entry.remaining = remaining
        entry.save(update_fields=["remaining"])
