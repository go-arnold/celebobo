from decimal import Decimal

from apps.sales.domain.enums import SalesPeriod
from apps.sales.domain.rules import (
    cents,
    commission_for,
    profit_for,
    proportional_reversal,
    refundable,
)


def test_commission_is_rounded_half_up():
    assert commission_for(Decimal("33.35"), Decimal("0.100")) == Decimal("3.34")


def test_reversal_is_proportional_and_capped():
    assert proportional_reversal(Decimal("20.00"), Decimal("50.00"), Decimal("200.00")) == Decimal(
        "5.00"
    )
    assert proportional_reversal(Decimal("20.00"), Decimal("900"), Decimal("200")) == Decimal(
        "20.00"
    )
    assert proportional_reversal(Decimal("0"), Decimal("10"), Decimal("100")) == Decimal("0.00")


def test_refundable_never_goes_negative():
    assert refundable(Decimal("100"), Decimal("30")) == Decimal("70")
    assert refundable(Decimal("100"), Decimal("130")) == Decimal("0.00")


def test_profit_requires_a_cost():
    assert profit_for(Decimal("100"), Decimal("80"), 3) == Decimal("60.00")
    assert profit_for(Decimal("100"), None, 3) is None


def test_helpers():
    assert cents(Decimal("1.005")) == Decimal("1.01")
    assert SalesPeriod("30d").days == 30
