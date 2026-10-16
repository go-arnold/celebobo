import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


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
    cashback_used: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Balance:
    eligible: bool
    available: Decimal
    pending: Decimal
    next_expiry: datetime | None


def share(amount: Decimal, percent: Decimal) -> Decimal:
    return (amount * percent / 100).quantize(CENT, rounding=ROUND_DOWN)


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)
