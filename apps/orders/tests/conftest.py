from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory

ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Gombe",
    "city": "Kinshasa",
    "country": "RD Congo",
}


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def shopper(db) -> User:
    return UserFactory.create(
        email="aline@celebobo.test",
        first_name="Aline",
        last_name="Mbuyi",
        phone_number="+243 81 000 0001",
    )


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(first_name="Patrick", last_name="Kabasele")


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create(first_name="Joël")


@pytest.fixture
def phone(db) -> Product:
    return ProductFactory.create(
        name="Galaxy A55", slug="galaxy-a55", price=Decimal("120.00"), stock=5
    )


@pytest.fixture
def as_user(api: APIClient) -> Callable[[User], APIClient]:
    def authenticate(user: User) -> APIClient:
        api.force_authenticate(user)
        return api

    return authenticate


@pytest.fixture
def place_order(as_user) -> Callable[..., dict[str, Any]]:
    counter = iter(range(1, 10_000))

    def place(user: User, product: Product, quantity: int = 1, **overrides: Any) -> dict[str, Any]:
        payload = {
            "lines": [{"product_id": product.pk, "quantity": quantity}],
            "payment_method": "orange_money",
            "address": ADDRESS,
            **overrides,
        }
        response = as_user(user).post(
            "/api/v1/orders/", payload, HTTP_IDEMPOTENCY_KEY=f"checkout-{next(counter):06d}"
        )
        assert response.status_code == 201, response.json()
        body: dict[str, Any] = response.json()
        return body

    return place
