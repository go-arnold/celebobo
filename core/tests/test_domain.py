from decimal import Decimal

import pytest

from core.domain import Actor, Conflict, InvalidTransition, Money, Role
from core.domain.money import CurrencyMismatchError


class TestRole:
    @pytest.mark.parametrize(
        ("role", "other", "expected"),
        [
            (Role.ADMIN, Role.MANAGER, True),
            (Role.MANAGER, Role.RESELLER, True),
            (Role.RESELLER, Role.MANAGER, False),
            (Role.CLIENT, Role.ANONYMOUS, True),
            (Role.ANONYMOUS, Role.CLIENT, False),
            (Role.SYSTEM, Role.ADMIN, True),
        ],
    )
    def test_hierarchy(self, role, other, expected):
        assert role.includes(other) is expected


class TestActor:
    def test_anonymous(self):
        actor = Actor.anonymous()

        assert not actor.is_authenticated
        assert not actor.owns(None)

    @pytest.mark.parametrize(
        ("role", "backoffice", "staff"),
        [
            (Role.CLIENT, False, False),
            (Role.RESELLER, True, False),
            (Role.MANAGER, True, True),
            (Role.ADMIN, True, True),
        ],
    )
    def test_capabilities(self, role, backoffice, staff):
        actor = Actor(role=role, user_id=7)

        assert actor.is_backoffice is backoffice
        assert actor.is_staff is staff
        assert actor.owns(7)
        assert not actor.owns(8)


class TestMoney:
    def test_quantizes_to_cents(self):
        assert Money(Decimal("10.005")).amount == Decimal("10.01")
        assert Money(Decimal("2.5")).amount == Decimal("2.50")

    def test_arithmetic(self):
        price = Money(Decimal("19.99"))

        assert price * 3 == Money(Decimal("59.97"))
        assert 2 * price == Money(Decimal("39.98"))
        assert price + Money(Decimal("0.01")) == Money(Decimal(20))
        assert (price - Money(Decimal(20))).is_negative
        assert -price == Money(Decimal("-19.99"))
        assert Money.total([price, price]) == Money(Decimal("39.98"))
        assert Money.zero().is_zero

    def test_comparisons(self):
        assert Money(Decimal(1)) < Money(Decimal(2)) <= Money(Decimal(2))
        assert Money(Decimal(3)) > Money(Decimal(2)) >= Money(Decimal(2))

    def test_rejects_mixed_currencies(self):
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal(1), "USD") + Money(Decimal(1), "CDF")

    def test_rejects_invalid_currency(self):
        with pytest.raises(ValueError, match="ISO 4217"):
            Money(Decimal(1), "usd")


class TestDomainErrors:
    def test_defaults_come_from_class(self):
        error = InvalidTransition()

        assert error.code == "invalid_transition"
        assert error.detail == InvalidTransition.default_detail
        assert dict(error.errors) == {}

    def test_overrides(self):
        error = Conflict("Déjà converti.", code="already_converted", meta={"order_id": 4})

        assert error.code == "already_converted"
        assert str(error) == "Déjà converti."
        assert error.meta["order_id"] == 4
