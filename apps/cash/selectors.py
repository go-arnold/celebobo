from django.db.models import F

from apps.cash.models import CashCollection, CashRemittance


class CashSelector:
    # still owed, oldest due first
    def open_collections(self, reseller_id: int, *, limit: int = 100) -> list[CashCollection]:
        return list(
            CashCollection.objects.filter(
                reseller_id=reseller_id, voided_at__isnull=True, covered__lt=F("amount")
            ).order_by("due_at", "pk")[:limit]
        )

    def remittances(self, reseller_id: int, *, limit: int = 20) -> list[CashRemittance]:
        return list(CashRemittance.objects.filter(reseller_id=reseller_id)[:limit])

    # resellers who hold cash now
    def holders(self) -> list[int]:
        return list(
            CashCollection.objects.filter(voided_at__isnull=True, covered__lt=F("amount"))
            .values_list("reseller_id", flat=True)
            .distinct()
        )
