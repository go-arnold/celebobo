from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Order
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def client_user(transactional_db) -> User:
    return UserFactory.create(email="aline@celebobo.test", first_name="Aline", last_name="Mbuyi")


@pytest.fixture
def reseller(transactional_db) -> User:
    return ResellerFactory.create(
        email="patrick@celebobo.test", first_name="Patrick", last_name="Kabasele"
    )


@pytest.fixture
def manager(transactional_db) -> User:
    return ManagerFactory.create(email="joel@celebobo.test", first_name="Joël")


@pytest.fixture
def product(transactional_db) -> Product:
    return ProductFactory.create(name="Galaxy A55", price=Decimal("120.00"), stock=10)


@pytest.fixture
def as_user() -> Callable[[User], APIClient]:
    def authenticate(user: User) -> APIClient:
        api = APIClient()
        api.force_authenticate(user)
        return api

    return authenticate


@pytest.fixture
def place_order(as_user, product) -> Callable[..., Order]:
    counter = iter(range(1, 10_000))

    def place(user: User, quantity: int = 1) -> Order:
        response = as_user(user).post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": product.pk, "quantity": quantity}],
                "payment_method": "cash",
                "address": ADDRESS,
            },
            HTTP_IDEMPOTENCY_KEY=f"messaging-{next(counter):06d}",
        )
        assert response.status_code == 201, response.json()
        return Order.objects.get(number=response.json()["number"])

    return place


@pytest.fixture
def assigned_order(as_user, manager, reseller, client_user, place_order) -> Order:
    order: Order = place_order(client_user)
    response = as_user(manager).post(
        f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk}
    )
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    return order


def thread_of(order: Order) -> Any:
    from apps.messaging.models import Conversation

    return Conversation.objects.get(order=order)
