import re
from decimal import Decimal

import pytest

from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.numbers import new_order_number, normalize_order_number
from apps.orders.domain.pricing import QuoteLine, ShippingRules, quote
from apps.orders.domain.state_machine import OrderState, OrderStateMachine, TransitionPolicyFactory
from core.domain.actor import Actor, Role
from core.domain.errors import InvalidTransition

CLIENT = Actor(Role.CLIENT, 1)
STRANGER = Actor(Role.CLIENT, 9)
RESELLER = Actor(Role.RESELLER, 2)
OTHER_RESELLER = Actor(Role.RESELLER, 3)
MANAGER = Actor(Role.MANAGER, 4)

S = OrderStatus
machine = OrderStateMachine(TransitionPolicyFactory())


def state(status: OrderStatus, reseller_id: int | None = 2) -> OrderState:
    return OrderState(status=status, client_id=1, reseller_id=reseller_id)


class TestStateMachine:
    @pytest.mark.parametrize(
        ("actor", "status", "expected"),
        [
            (CLIENT, S.PENDING, {S.CANCELLED}),
            (CLIENT, S.ASSIGNED, set()),
            (STRANGER, S.PENDING, set()),
            (RESELLER, S.ASSIGNED, {S.CONFIRMED}),
            (RESELLER, S.CONFIRMED, {S.PAID}),
            (RESELLER, S.PAID, {S.SHIPPING}),
            (RESELLER, S.SHIPPING, {S.DELIVERED}),
            (RESELLER, S.DELIVERED, set()),
            (OTHER_RESELLER, S.ASSIGNED, set()),
            (MANAGER, S.PENDING, {S.CONFIRMED, S.PAID, S.SHIPPING, S.DELIVERED, S.CANCELLED}),
            (MANAGER, S.SHIPPING, {S.DELIVERED, S.CANCELLED}),
            (MANAGER, S.DELIVERED, {S.RETURNED}),
            (MANAGER, S.CANCELLED, set()),
            (MANAGER, S.RETURNED, set()),
            (Actor.anonymous(), S.PENDING, set()),
        ],
    )
    def test_allowed_targets(self, actor, status, expected):
        assert machine.allowed(state(status), actor) == expected

    def test_resellers_cannot_act_on_unassigned_pending_orders(self):
        assert machine.allowed(state(S.PENDING, reseller_id=None), RESELLER) == set()

    def test_ensure_raises_with_context(self):
        with pytest.raises(InvalidTransition) as error:
            machine.ensure(state(S.ASSIGNED), S.DELIVERED, RESELLER)

        assert error.value.meta == {"from": "assigned", "to": "delivered"}

    def test_final_statuses(self):
        assert {status for status in OrderStatus if status.is_final} == {
            S.DELIVERED,
            S.CANCELLED,
            S.RETURNED,
        }


RULES = ShippingRules(free_threshold=Decimal(199), flat_fee=Decimal("2.98"))


def line(price: str, quantity: int = 1, *, free: bool = False, fee: str | None = None) -> QuoteLine:
    return QuoteLine(
        unit_price=Decimal(price),
        quantity=quantity,
        free_shipping=free,
        shipping_fee=Decimal(fee) if fee else None,
    )


class TestPricing:
    def test_flat_fee_below_threshold(self):
        result = quote([line("50.00", 2)], RULES)

        assert result.subtotal == Decimal("100.00")
        assert result.shipping_fee == Decimal("2.98")
        assert result.total == Decimal("102.98")
        assert result.free_shipping_remaining == Decimal("99.00")

    def test_free_above_threshold(self):
        result = quote([line("199.00")], RULES)

        assert result.shipping_fee == Decimal(0)
        assert result.free_shipping_remaining == Decimal(0)

    def test_free_when_every_line_ships_free(self):
        assert quote([line("10.00", free=True)], RULES).shipping_fee == Decimal(0)

    def test_highest_product_fee_wins(self):
        result = quote([line("10.00", fee="7.50"), line("10.00"), line("5.00", free=True)], RULES)

        assert result.shipping_fee == Decimal("7.50")


class TestOrderNumbers:
    def test_format(self):
        assert re.fullmatch(r"CB-[A-Z2-9]{4}-[A-Z2-9]{4}", new_order_number())
        assert len({new_order_number() for _ in range(500)}) == 500

    def test_normalize(self):
        assert normalize_order_number("  cb-ab12-cd34 ") == "CB-AB12-CD34"
