from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet, Sum

from apps.sales.domain.enums import CommissionKind
from apps.sales.domain.payouts import StatementStatus
from apps.sales.models import (
    CommissionEntry,
    DeliveryCredit,
    Payout,
    PayoutStatement,
    Refund,
    Sale,
)


class SaleRepository:
    def create(self, **fields: Any) -> Sale:
        return Sale.objects.create(**fields)

    def get(self, sale_id: int, *, for_update: bool = False) -> Sale | None:
        sales = Sale.objects.select_for_update() if for_update else Sale.objects
        return sales.filter(pk=sale_id).first()

    def save(self, sale: Sale, *, fields: Iterable[str]) -> None:
        sale.save(update_fields=[*fields])

    def delete(self, sale: Sale) -> None:
        sale.delete()

    def converted_item_ids(self, item_ids: Iterable[int]) -> set[int]:
        return set(
            Sale.objects.filter(order_item_id__in=list(item_ids)).values_list(
                "order_item_id", flat=True
            )
        )

    def for_order(self, order_id: int, *, for_update: bool = False) -> list[Sale]:
        sales = Sale.objects.select_for_update() if for_update else Sale.objects
        return list(sales.filter(order_id=order_id))

    def for_item(self, order_item_id: int) -> Sale | None:
        return Sale.objects.select_for_update().filter(order_item_id=order_item_id).first()

    def add_refund(self, sale: Sale, **fields: Any) -> Refund:
        return Refund.objects.create(sale=sale, **fields)


class CommissionRepository:
    def add(self, **fields: Any) -> CommissionEntry:
        return CommissionEntry.objects.create(**fields)

    def net_for_sale(self, sale: Sale) -> Decimal:
        total = CommissionEntry.objects.filter(sale=sale).aggregate(total=Sum("amount"))["total"]
        return Decimal(total or 0)

    # the commission currently earned: a price edit voids it and earns a new one
    def last_earned(self, sale: Sale) -> CommissionEntry | None:
        return (
            CommissionEntry.objects.filter(sale=sale, kind=CommissionKind.EARNED.value)
            .order_by("-pk")
            .first()
        )

    def available_at(self, sale: Sale) -> datetime | None:
        return (
            CommissionEntry.objects.filter(sale=sale, kind=CommissionKind.EARNED.value)
            .order_by("pk")
            .values_list("available_at", flat=True)
            .first()
        )

    def detach_sale(self, sale: Sale) -> None:
        CommissionEntry.objects.filter(sale=sale).update(sale=None)


class PayoutRepository:
    def create(self, **fields: Any) -> Payout:
        return Payout.objects.create(**fields)


class DeliveryCreditRepository:
    def add(self, **fields: Any) -> DeliveryCredit:
        return DeliveryCredit.objects.create(**fields)

    def for_order(self, order_id: int, kind: str) -> DeliveryCredit | None:
        return (
            DeliveryCredit.objects.select_for_update().filter(order_id=order_id, kind=kind).first()
        )


def _total(queryset: QuerySet[Any]) -> Decimal:
    return Decimal(queryset.aggregate(total=Sum("amount"))["total"] or 0)


class StatementRepository:
    """Payout statements, and the ledger lines they settle."""

    def reseller_ids(self) -> list[int]:
        ids = set(CommissionEntry.objects.values_list("reseller_id", flat=True).distinct())
        ids |= set(DeliveryCredit.objects.values_list("reseller_id", flat=True).distinct())
        return sorted(ids)

    def lock(self, statement_id: int) -> PayoutStatement | None:
        return PayoutStatement.objects.select_for_update().filter(pk=statement_id).first()

    def exists_for(self, reseller_id: int, payout_date: date) -> bool:
        return (
            PayoutStatement.objects.filter(reseller_id=reseller_id, payout_date=payout_date)
            .exclude(status=StatementStatus.CANCELLED.value)
            .exists()
        )

    def prepared(self, reseller_id: int) -> list[PayoutStatement]:
        return list(
            PayoutStatement.objects.select_for_update().filter(
                reseller_id=reseller_id, status=StatementStatus.PREPARED.value
            )
        )

    # validated before the cutoff and not settled yet
    def unsettled(
        self, reseller_id: int, cutoff: datetime
    ) -> tuple[list[CommissionEntry], list[DeliveryCredit]]:
        lines = {"reseller_id": reseller_id, "statement__isnull": True, "available_at__lt": cutoff}
        return (
            list(CommissionEntry.objects.select_for_update().filter(**lines)),
            list(DeliveryCredit.objects.select_for_update().filter(**lines)),
        )

    def create(self, **fields: Any) -> PayoutStatement:
        return PayoutStatement.objects.create(**fields)

    def save(self, statement: PayoutStatement, *, fields: Iterable[str]) -> None:
        statement.save(update_fields=[*fields])

    def settle(
        self,
        statement: PayoutStatement,
        entries: Iterable[CommissionEntry],
        credits: Iterable[DeliveryCredit],
    ) -> None:
        CommissionEntry.objects.filter(pk__in=[entry.pk for entry in entries]).update(
            statement=statement
        )
        DeliveryCredit.objects.filter(pk__in=[credit.pk for credit in credits]).update(
            statement=statement
        )

    def release(self, statement: PayoutStatement) -> None:
        CommissionEntry.objects.filter(statement=statement).update(statement=None)
        DeliveryCredit.objects.filter(statement=statement).update(statement=None)

    # later entries of a sale or an order that waits in a prepared statement (a reversal, a
    # rebased earning) join that statement
    def attach_reversals(self, statement: PayoutStatement) -> None:
        sale_ids = CommissionEntry.objects.filter(
            statement=statement, kind=CommissionKind.EARNED.value, sale__isnull=False
        ).values("sale_id")
        CommissionEntry.objects.filter(
            statement__isnull=True,
            reseller_id=statement.reseller_id,
            sale_id__in=sale_ids,
        ).update(statement=statement)
        order_ids = DeliveryCredit.objects.filter(statement=statement, order__isnull=False).values(
            "order_id"
        )
        DeliveryCredit.objects.filter(
            statement__isnull=True, reseller_id=statement.reseller_id, order_id__in=order_ids
        ).update(statement=statement)

    def totals(self, statement: PayoutStatement) -> tuple[Decimal, Decimal]:
        return (
            _total(CommissionEntry.objects.filter(statement=statement)),
            _total(DeliveryCredit.objects.filter(statement=statement)),
        )

    # what can be paid now: validated commissions and delivery fees, minus what was paid
    def due(self, reseller_id: int, at: datetime) -> Decimal:
        validated = _total(
            CommissionEntry.objects.filter(reseller_id=reseller_id, available_at__lte=at)
        )
        fees = _total(DeliveryCredit.objects.filter(reseller_id=reseller_id, available_at__lte=at))
        paid = _total(Payout.objects.filter(reseller_id=reseller_id))
        return validated + fees - paid
