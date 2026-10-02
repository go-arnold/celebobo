from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, ResellerFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.orders.tests.conftest import api, as_user

__all__ = ["api", "as_user"]


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create(first_name="Ada", last_name="Admin")


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create(first_name="Joël", last_name="Mpiana")


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create()


@pytest.fixture
def phone(db) -> Product:
    return ProductFactory.create(name="Galaxy A55", price=Decimal("120.00"), stock=10)
