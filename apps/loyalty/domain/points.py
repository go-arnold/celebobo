import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
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
    # 0.3 % of an invited client's invoice, for the reseller who invited them
    REFERRAL = "referral"
    REFERRAL_REVERSAL = "referral_reversal"


CREDITS = (EntryKind.EARN, EntryKind.REFUND, EntryKind.REFERRAL)
# movements following something the client did (an order, a return): expiry and the referral
# points of resellers are not the client's activity (account retention)
CLIENT_MOVEMENTS = (EntryKind.EARN, EntryKind.SPEND, EntryKind.REFUND, EntryKind.REVERSAL)
# credited on delivery, pending until the return period is over
EARNINGS = (EntryKind.EARN, EntryKind.REFERRAL)
# an invitee's order: its number stays off the reseller's history, which would otherwise give
# back each invitee's purchase total (privacy policy, 4)
REFERRALS = (EntryKind.REFERRAL, EntryKind.REFERRAL_REVERSAL)


@dataclass(frozen=True, slots=True, kw_only=True)
class Purchase:
    client_id: int
    base: Decimal
    points_used: Decimal
    discount: Decimal = ZERO
    placed_at: datetime | None = None

    # paid only in cash or Mobile Money: no points, no coupon (owner rule on non-real money)
    @property
    def real_money_only(self) -> bool:
        return self.points_used == 0 and self.discount == 0


@dataclass(frozen=True, slots=True, kw_only=True)
class Referral:
    reseller_id: int
    since: datetime


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


# referral points round to the nearest cent, as in the reseller policy's examples
def referral_share(base: Decimal, percent: Decimal) -> Decimal:
    return (base * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
