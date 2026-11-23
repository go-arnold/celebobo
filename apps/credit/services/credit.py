from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from django.db.models import F, QuerySet, Sum

from apps.credit.domain.rules import ZERO, EntryKind, expiry_of
from apps.credit.models import CreditEntry
from apps.credit.repositories import CreditRepository


class StoreCreditService:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._credits = CreditRepository()

    def _live(self, user_id: int) -> QuerySet[CreditEntry]:
        return self._credits.live(user_id, self._clock())

    def available(self, user_id: int, *, lock: bool = False) -> Decimal:
        rows = self._live(user_id)
        if lock:
            rows = rows.select_for_update()
            return sum((row.remaining for row in rows), ZERO)
        return rows.aggregate(total=Sum("remaining"))["total"] or ZERO

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return max(min(self.available(user_id, lock=lock), base), ZERO)

    def issue(
        self, user_id: int, amount: Decimal, *, note: str, order_id: int | None = None
    ) -> CreditEntry | None:
        if amount <= 0:
            return None
        now = self._clock()
        return CreditEntry.objects.create(
            user_id=user_id,
            kind=EntryKind.ISSUED.value,
            amount=amount,
            remaining=amount,
            expires_at=expiry_of(now),
            order_id=order_id,
            note=note[:200],
        )

    # the credit closest to its expiry is used first
    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        left = amount
        for credit in self._live(user_id).select_for_update().order_by("expires_at", "pk"):
            if left <= 0:
                break
            used = min(credit.remaining, left)
            credit.remaining -= used
            credit.save(update_fields=["remaining"])
            CreditEntry.objects.create(
                user_id=user_id,
                kind=EntryKind.SPENT.value,
                amount=-used,
                source=credit,
                unreturned=used,
                order_id=order_id,
            )
            left -= used

    # the order was cancelled or returned, or part of it: credit goes back to the credit it came
    # from, which keeps its expiry (the latest spending first)
    def give_back(self, order_id: int, amount: Decimal | None = None, *, note: str = "") -> Decimal:
        spendings = (
            CreditEntry.objects.select_for_update(of=("self",))
            .filter(order_id=order_id, kind=EntryKind.SPENT.value, unreturned__gt=0)
            .select_related("source")
            .order_by("-pk")
        )
        left = sum((row.unreturned for row in spendings), ZERO) if amount is None else amount
        given = ZERO
        for spending in spendings:
            if left <= 0:
                break
            back = min(spending.unreturned, left)
            spending.unreturned -= back
            spending.save(update_fields=["unreturned"])
            source = spending.source
            if source is not None:
                CreditEntry.objects.filter(pk=source.pk).update(remaining=F("remaining") + back)
            CreditEntry.objects.create(
                user_id=spending.user_id,
                kind=EntryKind.RESTORED.value,
                amount=back,
                source=source,
                order_id=order_id,
                note=note[:200],
            )
            left -= back
            given += back
        return given

    def spent_on(self, order_id: int) -> Decimal:
        total = CreditEntry.objects.filter(order_id=order_id, kind=EntryKind.SPENT.value).aggregate(
            total=Sum("unreturned")
        )["total"]
        return total or ZERO

    # daily: what is left of a credit 6 months old is lost
    def expire(self) -> int:
        now = self._clock()
        expired = 0
        for credit in CreditEntry.objects.select_for_update().filter(
            kind=EntryKind.ISSUED.value, remaining__gt=0, expires_at__lte=now
        ):
            CreditEntry.objects.create(
                user_id=credit.user_id,
                kind=EntryKind.EXPIRED.value,
                amount=-credit.remaining,
                source=credit,
            )
            credit.remaining = ZERO
            credit.save(update_fields=["remaining"])
            expired += 1
        return expired
