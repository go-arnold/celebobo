from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, ResellerFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.orders.tests.conftest import api, as_user, place_order, shopper

__all__ = ["api", "as_user", "place_order", "shopper"]

SALES = "/api/v1/bo/sales/"


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(
        first_name="Patrick", last_name="Kabasele", commission_rate=Decimal("0.100")
    )


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create(first_name="Joël")


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def phone(db) -> Product:
    return ProductFactory.create(
        name="Galaxy A55",
        slug="galaxy-a55",
        price=Decimal("120.00"),
        cost_price=Decimal("80.00"),
        stock=10,
    )


@pytest.fixture
def record_sale(as_user, phone) -> Callable[..., dict[str, Any]]:
    counter = iter(range(1, 10_000))

    def record(user: User, product: Product | None = None, **overrides: Any) -> dict[str, Any]:
        payload = {
            "product_id": (product or phone).pk,
            "quantity": 2,
            "unit_price": "100.00",
            "payment_method": "cash",
            "sold_to": "  Jean   Mukendi ",
            **overrides,
        }
        response = as_user(user).post(
            SALES, payload, format="json", HTTP_IDEMPOTENCY_KEY=f"sale-{next(counter):06d}"
        )
        assert response.status_code == 201, response.json()
        body: dict[str, Any] = response.json()
        return body

    return record
