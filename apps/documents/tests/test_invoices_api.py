from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import ResellerFactory
from apps.documents.adapters.gateways import LoyaltyPointsStatements
from apps.loyalty.domain.points import InvoiceStatement
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


@pytest.fixture
def statement(monkeypatch) -> InvoiceStatement:
    printed = InvoiceStatement(
        earned=Decimal(12),
        earned_pending=True,
        used=Decimal(0),
        available=Decimal(0),
        orders_count=1,
        orders_total=Decimal(240),
        return_days=7,
    )
    monkeypatch.setattr(LoyaltyPointsStatements, "statement", lambda *_: printed)
    return printed


def test_invoice_prints_the_points_statement(as_user, manager, order, renderer, statement):
    as_user(manager).get(f"/api/v1/bo/orders/{order.pk}/invoice/")

    assert renderer.calls[0][1]["points"] == statement


# deleted or anonymised: the points history is gone, a statement would be recomputed wrongly
def test_no_points_statement_once_the_client_account_is_deleted(
    as_user, manager, order, renderer, statement
):
    User.objects.filter(pk=order.client_id).update(deleted_at=timezone.now())

    response = as_user(manager).get(f"/api/v1/bo/orders/{order.pk}/invoice/")

    assert response.status_code == 200
    assert renderer.calls[0][1]["points"] is None


def test_the_reseller_copy_has_no_points_statement_nor_contact_after_the_return_period(
    as_user, manager, reseller, order, renderer, *, monkeypatch
):
    from datetime import timedelta

    from django.utils import timezone

    from apps.documents.adapters.gateways import LoyaltyPointsStatements
    from apps.orders.models import OrderStatusEvent

    monkeypatch.setattr(LoyaltyPointsStatements, "statement", lambda *_: "statement")
    as_user(manager).post(f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk})
    as_user(manager).post(
        f"/api/v1/bo/orders/{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    OrderStatusEvent.objects.filter(order=order, to_status="delivered").update(
        created_at=timezone.now() - timedelta(days=8)
    )

    as_user(reseller).get(f"/api/v1/bo/orders/{order.pk}/invoice/")
    reseller_copy = renderer.calls[-1][1]
    as_user(manager).get(f"/api/v1/bo/orders/{order.pk}/invoice/")
    staff_copy = renderer.calls[-1][1]

    # the statement gives the client's purchase totals: not for the reseller (policy §4)
    assert reseller_copy["points"] is None
    assert reseller_copy["order"].contact_hidden is True
    assert reseller_copy["order"].address.phone == ""
    assert reseller_copy["order"].client.email is None
    assert staff_copy["points"] == "statement"
    assert staff_copy["order"].contact_hidden is False
    assert staff_copy["order"].address.phone == "+243 81 234 5678"


# warranty policy: the invoice carries each unit's serial number or IMEI and the warranty dates
def test_the_invoice_prints_serials_and_warranty_dates(as_user, manager, order, renderer):
    from datetime import timedelta

    from apps.orders.models import OrderItemSerial

    item = order.items.get()
    OrderItemSerial.objects.create(item=item, serial="352099001761481")
    staff = as_user(manager)

    staff.get(f"/api/v1/bo/orders/{order.pk}/invoice/")
    before = renderer.calls[-1][1]["warranty"]
    staff.post(
        f"/api/v1/bo/orders/{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    staff.get(f"/api/v1/bo/orders/{order.pk}/invoice/")
    context = renderer.calls[-1][1]

    assert context["order"].items[0].serials == ("352099001761481",)
    # before the delivery the durations, after it the dates
    assert (before.trial_days, before.warranty_months, before.trial_until) == (7, 1, None)
    today = timezone.localdate()
    assert context["warranty"].trial_until == today + timedelta(days=7)
    assert context["warranty"].warranty_until > context["warranty"].trial_until
