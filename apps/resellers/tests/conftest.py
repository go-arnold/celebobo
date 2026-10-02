from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, ResellerFactory
from apps.orders.tests.conftest import api, as_user, phone, place_order, shopper

__all__ = ["api", "as_user", "phone", "place_order", "shopper"]

APPLICATION = {
    "first_name": " Grâce ",
    "last_name": "Ilunga",
    "email": "Grace.Ilunga@Example.com",
    "phone_number": "+243 82 555 0101",
    "city": "Lubumbashi",
    "message": "Je vends déjà des téléphones à mon entourage.",
}


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create(first_name="Joël", last_name="Mpiana")


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(
        first_name="Patrick",
        last_name="Kabasele",
        referral_code="4821",
        commission_rate=Decimal("0.100"),
    )
