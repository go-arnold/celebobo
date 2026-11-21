from decimal import Decimal

import pytest

from apps.sales.domain.enums import CommissionRule, SalesPeriod
from apps.sales.domain.rules import (
    Commission,
    CommissionLine,
    cents,
    line_commission,
    profit_for,
    proportional_reversal,
    refundable,
)


def celebobo(paid: str, cost: str | None, quantity: int = 1) -> Commission:
    return line_commission(
        CommissionLine(
            paid=Decimal(paid),
            quantity=quantity,
            unit_cost=None if cost is None else Decimal(cost),
        )
    )


def partner(paid: str, gain: str | None, quantity: int = 1) -> Commission:
    return line_commission(
        CommissionLine(
            paid=Decimal(paid),
            quantity=quantity,
            unit_cost=Decimal("1.00"),
            partner=True,
            partner_gain=None if gain is None else Decimal(gain),
        )
    )


class TestCelebobo:
    def test_ten_percent_when_the_margin_is_wide(self):
        # margin 40 -> half is 20, 10 % of 100 is 10
        assert celebobo("100.00", "60.00") == Commission(Decimal("10.00"), CommissionRule.PAID)

    def test_capped_at_half_the_margin(self):
        # margin 12 -> half is 6, below 10 % of 100
        assert celebobo("100.00", "88.00") == Commission(Decimal("6.00"), CommissionRule.MARGIN)

    def test_margin_counts_every_unit(self):
        # 3 units paid 75, cost 3 x 23 = 69, margin 6 -> 3.00 (10 % would be 7.50)
        assert celebobo("75.00", "23.00", 3) == Commission(Decimal("3.00"), CommissionRule.MARGIN)

    @pytest.mark.parametrize("cost", ["100.00", "120.00"])
    def test_nothing_without_a_margin(self, cost):
        assert celebobo("100.00", cost).amount == Decimal("0.00")

    def test_unknown_cost_pays_ten_percent(self):
        assert celebobo("100.00", None) == Commission(Decimal("10.00"), CommissionRule.UNKNOWN_COST)

    def test_rounded_half_up_to_the_cent(self):
        assert celebobo("33.35", None).amount == Decimal("3.34")
        # margin 0.05 -> half is 0.025 -> 0.03
        assert celebobo("10.00", "9.95").amount == Decimal("0.03")


class TestPartner:
    def test_capped_at_a_fifth_of_celebobo_gain(self):
        # gain 7.50 -> 1.50, below 10 % of 50
        assert partner("50.00", "7.50") == Commission(Decimal("1.50"), CommissionRule.PARTNER_GAIN)

    def test_ten_percent_when_the_gain_is_high(self):
        # gain 12 -> 2.40, above 10 % of 20
        assert partner("20.00", "12.00") == Commission(Decimal("2.00"), CommissionRule.PAID)

    def test_gain_counts_every_unit(self):
        # 2 nights at 80: gain 2 x 8 = 16 -> 3.20 (10 % would be 16)
        assert partner("160.00", "8.00", 2).amount == Decimal("3.20")

    def test_the_cost_is_ignored(self):
        line = CommissionLine(
            paid=Decimal("50.00"),
            quantity=1,
            unit_cost=Decimal("49.00"),
            partner=True,
            partner_gain=Decimal("7.50"),
        )

        assert line_commission(line).amount == Decimal("1.50")

    def test_no_gain_no_commission(self):
        assert partner("50.00", None).amount == Decimal("0.00")


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
