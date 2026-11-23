"""Cagnotte operations (loyalty policy, "Cagnotte : des bonus en plus de vos points").

Time-limited operations on top of the 1 % points, never instead of them: an immediate discount,
a cashback or boosted points, with their conditions (dates, products concerned, minimum purchase,
cap, how the cashback is paid, how long Cagnotte points stay valid).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MIN_PERCENT = Decimal("0.01")
MAX_PERCENT = Decimal("50.00")
VALID_DAYS = (1, 730)


class CampaignKind(StrEnum):
    # paid at checkout: a percentage off the products concerned (non-real money, like a coupon)
    DISCOUNT = "discount"
    # after delivery and the trial: a percentage of what was really paid, by Mobile Money or points
    CASHBACK = "cashback"
    # after delivery and the trial: extra points, on top of the 1 %
    BOOSTED_POINTS = "boosted_points"

    @property
    def label(self) -> str:
        return KIND_LABELS[self]


KIND_LABELS = {
    CampaignKind.DISCOUNT: "Remise immédiate",
    CampaignKind.CASHBACK: "Cashback",
    CampaignKind.BOOSTED_POINTS: "Points majorés",
}


class Payout(StrEnum):
    POINTS = "points"
    # sent by staff by M-Pesa or Airtel Money once the trial is over
    MOBILE_MONEY = "mobile_money"


class RewardStatus(StrEnum):
    # paid in points: the loyalty ledger holds them (pending, then spendable)
    CREDITED = "credited"
    # cashback by Mobile Money, for staff to send once the trial is over
    TO_PAY = "to_pay"
    PAID = "paid"
    # the order was cancelled or returned before anything was paid
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class Terms:
    kind: CampaignKind
    percent: Decimal
    min_purchase: Decimal | None
    cap: Decimal | None


def advantage(terms: Terms, eligible: Decimal) -> Decimal:
    """What the operation gives on ``eligible`` (the products concerned), to the cent below.

    Nothing below the minimum purchase; never more than the cap.
    """
    if eligible <= 0 or (terms.min_purchase is not None and eligible < terms.min_purchase):
        return ZERO
    amount = (eligible * terms.percent / 100).quantize(CENT, rounding=ROUND_DOWN)
    if terms.cap is not None:
        amount = min(amount, terms.cap)
    return max(amount, ZERO)


@dataclass(frozen=True, slots=True, kw_only=True)
class Scope:
    """The products concerned: everything when no category and no product is chosen."""

    category_ids: frozenset[int]
    product_ids: frozenset[int]

    @property
    def everything(self) -> bool:
        return not self.category_ids and not self.product_ids

    def covers(self, product_id: int | None, categories: Iterable[int]) -> bool:
        if product_id is None:
            return False
        if self.everything or product_id in self.product_ids:
            return True
        return any(category in self.category_ids for category in categories)


def overlaps(
    starts_at: datetime, ends_at: datetime, others: Sequence[tuple[datetime, datetime]]
) -> bool:
    """One operation at a time: the periods may touch, not overlap."""
    return any(start < ends_at and starts_at < end for start, end in others)
