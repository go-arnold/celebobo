from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, ResellerFactory
from apps.analytics.repositories import FactsRefresher
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.orders.tests.conftest import api, as_user, place_order, shopper

__all__ = ["api", "as_user", "place_order", "shopper"]


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create()


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(first_name="Patrick", last_name="Kabasele")


@pytest.fixture
def phones(db):
    return CategoryFactory.create(name="Smartphones")


@pytest.fixture
def phone(phones) -> Product:
    return ProductFactory.create(
        name="Galaxy A55",
        category=phones,
        price=Decimal("120.00"),
        cost_price=Decimal("80.00"),
        stock=50,
    )


@pytest.fixture
def case(db) -> Product:
    return ProductFactory.create(
        name="Coque", price=Decimal("10.00"), cost_price=Decimal("4.00"), stock=50
    )


@pytest.fixture
def now() -> datetime:
    return timezone.localtime()


@pytest.fixture
def sell(as_user, now) -> Callable[..., dict[str, Any]]:
    counter = iter(range(1, 10_000))

    def record(
        seller: User,
        product: Product,
        *,
        days_ago: float = 0,
        quantity: int = 1,
        unit_price: str = "100.00",
        payment_method: str = "cash",
    ) -> dict[str, Any]:
        response = as_user(seller).post(
            "/api/v1/bo/sales/",
            {
                "product_id": product.pk,
                "quantity": quantity,
                "unit_price": unit_price,
                "payment_method": payment_method,
                "sold_at": (now - timedelta(days=days_ago, minutes=1)).isoformat(),
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"analytics-sale-{next(counter):06d}",
        )
        assert response.status_code == 201, response.json()
        body: dict[str, Any] = response.json()
        return body

    return record


@pytest.fixture
def refresh() -> Callable[[], None]:
    return FactsRefresher().refresh


@pytest.fixture
def products(phone: Product, case: Product) -> tuple[Product, Product]:
    return phone, case


@pytest.fixture
def activity(sell, refresh, reseller, manager, products) -> None:
    phone, case = products
    sell(reseller, phone, days_ago=1, quantity=2)
    sell(reseller, case, unit_price="10.00", payment_method="orange_money")
    sell(manager, phone, days_ago=10, unit_price="120.00")
    refresh()
