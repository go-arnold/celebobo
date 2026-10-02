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


class SalesPeriod(StrEnum):
    LAST_2_DAYS = "2d"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"

    @property
    def days(self) -> int:
        return int(self.value.removesuffix("d"))
