import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminFactory

pytestmark = pytest.mark.django_db

HUGE = "99999999999999999999"


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/products/?ids={HUGE}",
        f"/api/v1/products/?page={HUGE}",
        f"/api/v1/products/?page_size={HUGE}",
    ],
)
def test_oversized_integers_are_rejected(path):
    assert APIClient().get(path).status_code == 400


@pytest.mark.parametrize("path", [f"/api/v1/bo/products/{HUGE}/", "/api/v1/bo/orders/2147483648/"])
def test_oversized_path_ids_do_not_match(path):
    api = APIClient()
    api.force_authenticate(AdminFactory.create())

    assert api.get(path).status_code == 404


def test_oversized_body_integers_are_rejected():
    api = APIClient()
    api.force_authenticate(AdminFactory.create())

    response = api.post(
        "/api/v1/checkout/quote/", {"lines": [{"product_id": HUGE, "quantity": 1}]}, format="json"
    )

    assert response.status_code == 400
