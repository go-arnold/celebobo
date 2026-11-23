"""Store credit (avoir), decided by the owner on 18 Nov 2026: a balance in dollars, separate from
the points, that pays products and delivery, valid 6 months; non-real money (no commission, no
referral points). The warranty policy issues it for a change of mind during the trial."""

import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

VALIDITY_MONTHS = 6
ZERO = Decimal("0.00")


class EntryKind(StrEnum):
    # credit given to the client (a change of mind during the trial)
    ISSUED = "issued"
    # used on an order
    SPENT = "spent"
    # given back: the order was cancelled or returned, or its price went down
    RESTORED = "restored"
    # not used within 6 months
    EXPIRED = "expired"

    @property
    def label(self) -> str:
        return LABELS[self]


LABELS = {
    EntryKind.ISSUED: "Avoir reçu",
    EntryKind.SPENT: "Avoir utilisé",
    EntryKind.RESTORED: "Avoir rendu",
    EntryKind.EXPIRED: "Avoir expiré",
}


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    return moment.replace(
        year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1])
    )


def expiry_of(issued_at: datetime) -> datetime:
    return add_months(issued_at, VALIDITY_MONTHS)


@dataclass(frozen=True, slots=True, kw_only=True)
class Movement:
    kind: EntryKind
    amount: Decimal
    at: datetime
    order_number: str | None
    expires_at: datetime | None
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CreditBalance:
    available: Decimal
    next_expiry: datetime | None
    history: tuple[Movement, ...]
