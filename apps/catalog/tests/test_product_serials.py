"""Products whose units each get a serial number or IMEI (warranty policy), set by staff."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/bo/products/"


@pytest.fixture
def staff_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(ManagerFactory.create())
    return api


def test_off_by_default_and_set_on_creation(staff_api):
    category = CategoryFactory.create(name="Smartphones", slug="smartphones")
    payload = {
        "name": "Galaxy A35",
        "description": "Un smartphone vendu avec son IMEI sur la facture.",
        "category_id": category.pk,
        "price": "250.00",
        "stock": 3,
    }

    plain = staff_api.post(PRODUCTS, payload, format="json").json()
    tracked = staff_api.post(
        PRODUCTS, {**payload, "name": "Galaxy A36", "serial_required": True}, format="json"
    ).json()

    assert plain["serial_required"] is False
    assert tracked["serial_required"] is True
    assert Product.objects.get(pk=tracked["id"]).serial_required is True


def test_switched_on_later_and_copied_with_the_product(staff_api):
    product = ProductFactory.create()

    body = staff_api.patch(
        f"{PRODUCTS}{product.pk}/", {"serial_required": True}, format="json"
    ).json()
    copy = staff_api.post(f"{PRODUCTS}{product.pk}/duplicate/").json()

    assert body["serial_required"] is True
    assert copy["serial_required"] is True
