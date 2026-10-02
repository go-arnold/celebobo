from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.db.models import Sum

from apps.sales.domain.enums import CommissionKind
from apps.sales.models import CommissionEntry, Payout, Refund, Sale


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

    def add_refund(self, sale: Sale, **fields: Any) -> Refund:
        return Refund.objects.create(sale=sale, **fields)


class CommissionRepository:
    def add(self, **fields: Any) -> CommissionEntry:
        return CommissionEntry.objects.create(**fields)

    def net_for_sale(self, sale: Sale) -> Decimal:
        total = CommissionEntry.objects.filter(sale=sale).aggregate(total=Sum("amount"))["total"]
        return Decimal(total or 0)

    def earned_rate(self, sale: Sale) -> Decimal | None:
        entry = (
            CommissionEntry.objects.filter(sale=sale, kind=CommissionKind.EARNED.value)
            .order_by("pk")
            .first()
        )
        return entry.rate if entry else None

    def balance(self, reseller_id: int) -> Decimal:
        earned = CommissionEntry.objects.filter(reseller_id=reseller_id).aggregate(
            total=Sum("amount")
        )["total"]
        paid = Payout.objects.filter(reseller_id=reseller_id).aggregate(total=Sum("amount"))[
            "total"
        ]
        return Decimal(earned or 0) - Decimal(paid or 0)

    def detach_sale(self, sale: Sale) -> None:
        CommissionEntry.objects.filter(sale=sale).update(sale=None)


class PayoutRepository:
    def create(self, **fields: Any) -> Payout:
        return Payout.objects.create(**fields)
