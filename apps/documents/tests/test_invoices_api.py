import pytest

from apps.accounts.tests.factories import ResellerFactory
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])


def test_clients_download_their_invoice(as_user, shopper, order):
    response = as_user(shopper).get(f"/api/v1/me/orders/{order.number}/invoice/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert f"facture-{order.number}.pdf" in response["Content-Disposition"]


def test_invoice_content(as_user, manager, order, renderer):
    as_user(manager).get(f"/api/v1/bo/orders/{order.pk}/invoice/")

    template, context = renderer.calls[0]
    assert template == "documents/invoice.html"
    assert context["order"].summary.number == order.number
    assert context["company_name"] == "Celebobo"


def test_invoices_are_scoped(as_user, order):
    reseller = ResellerFactory.create()

    assert as_user(reseller).get(f"/api/v1/bo/orders/{order.pk}/invoice/").status_code == 404


def test_other_clients_cannot_read_it(as_user, order):
    from apps.accounts.tests.factories import UserFactory

    response = as_user(UserFactory.create()).get(f"/api/v1/me/orders/{order.number}/invoice/")

    assert response.status_code == 404


def test_cancelled_orders_have_no_invoice(as_user, shopper, order, renderer):
    as_user(shopper).post(f"/api/v1/me/orders/{order.number}/cancel/", {"reason": "changed_mind"})

    response = as_user(shopper).get(f"/api/v1/me/orders/{order.number}/invoice/")

    assert response.status_code == 409
    assert response.json()["code"] == "invoice_unavailable"
