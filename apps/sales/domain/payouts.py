from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

# a commission stays pending through the 7-day trial period that follows the delivery (reseller
# policy, 4); a manual sale counts from its sale date
VALIDATION_DAYS = 7
# resellers are paid on the 1st and the 16th, from $5; below, the balance rolls over (policy, 5)
PAYOUT_DAYS = (1, 16)
PAYOUT_THRESHOLD = Decimal("5.00")


class CommissionStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    PAID = "paid"
    CANCELLED = "cancelled"


class StatementStatus(StrEnum):
    PREPARED = "prepared"
    PAID = "paid"
    # replaced by the statement of the next payout date before it was paid
    CANCELLED = "cancelled"


class DeliveryCreditKind(StrEnum):
    CREDIT = "credit"
    REVERSAL = "reversal"


class StatementLineKind(StrEnum):
    COMMISSION = "commission"
    REVERSAL = "reversal"
    DELIVERY_FEE = "delivery_fee"
    DELIVERY_FEE_REVERSAL = "delivery_fee_reversal"


@dataclass(frozen=True, slots=True)
class PayoutCalendar:
    days: tuple[int, ...] = PAYOUT_DAYS

    def is_payout_day(self, day: date) -> bool:
        return day.day in self.days

    # the payout date on or after this day
    def next(self, day: date) -> date:
        for payout_day in self.days:
            if day.day <= payout_day:
                return day.replace(day=payout_day)
        following = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
        return following.replace(day=self.days[0])

    # the payout date on or before this day
    def latest(self, day: date) -> date:
        for payout_day in reversed(self.days):
            if day.day >= payout_day:
                return day.replace(day=payout_day)
        previous = day.replace(day=1) - timedelta(days=1)
        return previous.replace(day=self.days[-1])


def payable(total: Decimal, threshold: Decimal = PAYOUT_THRESHOLD) -> bool:
    return total >= threshold
