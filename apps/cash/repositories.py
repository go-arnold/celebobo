from collections.abc import Iterable
from typing import Any

from django.db.models import F

from apps.cash.models import CashCollection, CashRemittance


class CashRepository:
    def collection_of(self, order_id: int, *, for_update: bool = False) -> CashCollection | None:
        rows = CashCollection.objects.select_for_update() if for_update else CashCollection.objects
        return rows.filter(order_id=order_id).first()

    def create_collection(self, **fields: Any) -> CashCollection:
        return CashCollection.objects.create(**fields)

    def save(self, collection: CashCollection, *, fields: Iterable[str]) -> None:
        collection.save(update_fields=[*fields])

    # still owed, oldest due first
    def open_collections(
        self, reseller_id: int, *, for_update: bool = False
    ) -> list[CashCollection]:
        rows = CashCollection.objects.select_for_update() if for_update else CashCollection.objects
        return list(
            rows.filter(reseller_id=reseller_id, voided_at__isnull=True)
            .filter(covered__lt=F("amount"))
            .order_by("due_at", "pk")
        )

    def open_collections_of(self, reseller_ids: Iterable[int]) -> list[CashCollection]:
        return list(
            CashCollection.objects.filter(
                reseller_id__in=list(reseller_ids), voided_at__isnull=True
            )
            .filter(covered__lt=F("amount"))
            .order_by("due_at", "pk")
        )

    def create_remittance(self, **fields: Any) -> CashRemittance:
        return CashRemittance.objects.create(**fields)
