from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory, ResellerFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.documents.services.contracts import PdfRenderer
from apps.orders.tests.conftest import api, as_user, place_order, shopper
from core.container import container

__all__ = ["api", "as_user", "place_order", "shopper"]


class RecordingRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def render(self, template: str, context: Mapping[str, Any]) -> bytes:
        self.calls.append((template, dict(context)))
        return b"%PDF-fake"


@pytest.fixture
def renderer() -> Iterator[RecordingRenderer]:
    fake = RecordingRenderer()
    with container.override(PdfRenderer, fake):
        yield fake


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create()


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def reseller(db) -> User:
    return ResellerFactory.create(first_name="Patrick", last_name="Kabasele")


@pytest.fixture
def phones(db):
    return CategoryFactory.create(name="Smartphones", slug="smartphones")


@pytest.fixture
def phone(phones) -> Product:
    return ProductFactory.create(
        name="Galaxy A55",
        slug="galaxy-a55",
        category=phones,
        price=Decimal("120.00"),
        cost_price=Decimal("80.00"),
        stock=20,
    )


@pytest.fixture
def sell(as_user) -> Callable[..., dict[str, Any]]:
    counter = iter(range(1, 10_000))

    def record(seller: User, product: Product, **overrides: Any) -> dict[str, Any]:
        response = as_user(seller).post(
            "/api/v1/bo/sales/",
            {
                "product_id": product.pk,
                "quantity": 1,
                "unit_price": "100.00",
                "payment_method": "cash",
                "sold_to": "Jean Mukendi",
                **overrides,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"documents-sale-{next(counter):06d}",
        )
        assert response.status_code == 201, response.json()
        body: dict[str, Any] = response.json()
        return body

    return record


@pytest.fixture
def run_jobs(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)
