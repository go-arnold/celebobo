from enum import StrEnum


class SaleStatus(StrEnum):
    VALID = "valid"
    REFUNDED = "refunded"
    RETURNED = "returned"


class RefundKind(StrEnum):
    REFUND = "refund"
    RETURN = "return"


class CommissionKind(StrEnum):
    EARNED = "earned"
    REVERSED = "reversed"


# which cap set an earned commission (rules decided on 16 Nov 2026, see rules.py)
class CommissionRule(StrEnum):
    # 10 % of the amount paid for the line
    PAID = "paid"
    # capped at 50 % of the gross margin (Celebobo products)
    MARGIN = "margin"
    # capped at 20 % of Celebobo's gain (partner products)
    PARTNER_GAIN = "partner_gain"
    # the product had no purchase price: 10 % of the amount paid
    UNKNOWN_COST = "unknown_cost"
    # entries written before 16 Nov 2026, with the reseller's own rate
    LEGACY_RATE = "legacy_rate"


class SalesPeriod(StrEnum):
    LAST_2_DAYS = "2d"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"

    @property
    def days(self) -> int:
        return int(self.value.removesuffix("d"))
