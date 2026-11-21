import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# months the points stay usable after the programme is switched off (loyalty policy)
CLOSING_MONTHS = 3


class EntryKind(StrEnum):
    EARN = "earn"
    SPEND = "spend"
    REFUND = "refund"
    REVERSAL = "reversal"
    EXPIRY = "expiry"


CREDITS = (EntryKind.EARN, EntryKind.REFUND)


@dataclass(frozen=True, slots=True, kw_only=True)
class Purchase:
    client_id: int
    base: Decimal
    points_used: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Balance:
    eligible: bool
    available: Decimal
    pending: Decimal
    # the whole balance expires then without a new purchase
    next_expiry: datetime | None
    # the programme is switched off: points are usable until then, no new earnings
    closes_at: datetime | None = None
    # delivered orders to date ("factures encaissées"), and the latest movements
    orders_count: int = 0
    orders_total: Decimal = ZERO
    history: tuple["Movement", ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class Movement:
    kind: EntryKind
    amount: Decimal
    at: datetime
    order_number: str | None
    # an earning still waiting for the end of the return period
    pending: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class InvoiceStatement:
    """The points lines printed on an invoice (loyalty policy, "Votre relevé")."""

    earned: Decimal
    earned_pending: bool
    used: Decimal
    available: Decimal
    orders_count: int
    orders_total: Decimal
    # earned points become usable this many days after delivery
    return_days: int


def share(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / 100).quantize(CENT, rounding=ROUND_DOWN)


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)
