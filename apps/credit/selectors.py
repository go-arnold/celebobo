from collections.abc import Callable
from datetime import datetime

from django.db.models import Sum

from apps.credit.domain.rules import ZERO, CreditBalance, EntryKind, Movement
from apps.credit.models import CreditEntry

HISTORY_SIZE = 50


class CreditSelector:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def balance(self, user_id: int) -> CreditBalance:
        live = CreditEntry.objects.filter(
            user_id=user_id,
            kind=EntryKind.ISSUED.value,
            remaining__gt=0,
            expires_at__gt=self._clock(),
        )
        first = live.order_by("expires_at").first()
        rows = (
            CreditEntry.objects.filter(user_id=user_id)
            .select_related("order")
            .order_by("-created_at", "-pk")[:HISTORY_SIZE]
        )
        return CreditBalance(
            available=live.aggregate(total=Sum("remaining"))["total"] or ZERO,
            next_expiry=first.expires_at if first is not None else None,
            history=tuple(
                Movement(
                    kind=EntryKind(row.kind),
                    amount=row.amount,
                    at=row.created_at,
                    order_number=row.order.number if row.order is not None else None,
                    expires_at=row.expires_at,
                    note=row.note,
                )
                for row in rows
            ),
        )
