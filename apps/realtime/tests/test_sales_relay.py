from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminFactory, ResellerFactory
from apps.analytics.facades import FactsFacade
from apps.catalog.tests.factories import ProductFactory
from apps.realtime.domain.groups import STAFF, user_group
from apps.realtime.domain.protocol import ServerEvent
from apps.realtime.tests.test_presence_api import authenticated, broadcaster
from core.container import container

__all__ = ["broadcaster"]

pytestmark = pytest.mark.django_db(transaction=True)


def test_sales_commissions_and_payouts_are_pushed(broadcaster):
    reseller = ResellerFactory.create(commission_rate=Decimal("0.100"))
    product = ProductFactory.create(stock=5)

    authenticated(reseller).post(
        "/api/v1/bo/sales/",
        {"product_id": product.pk, "quantity": 1, "unit_price": "100", "payment_method": "cash"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="relay-sale-0001",
    )
    authenticated(AdminFactory.create()).post(
        "/api/v1/bo/payouts/",
        {"reseller_id": reseller.pk, "amount": "4.00"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="relay-payout-01",
    )

    sent = {event: (groups, data) for groups, event, data in broadcaster.sent}
    groups, data = sent[ServerEvent.SALE_CREATED]
    assert set(groups) == {user_group(reseller.pk), STAFF}
    assert data["total"] == "100.00"
    assert sent[ServerEvent.COMMISSION_UPDATED] == (
        (user_group(reseller.pk),),
        {"reseller_id": reseller.pk, "delta": "10.00"},
    )
    assert sent[ServerEvent.PAYOUT_CREATED][1]["amount"] == "4.00"


def test_new_reseller_applications_reach_staff(broadcaster):
    APIClient().post(
        "/api/v1/reseller-applications/",
        {
            "first_name": "Grâce",
            "last_name": "Ilunga",
            "email": "grace@example.com",
            "phone_number": "+243 82 555 0101",
            "city": "Kolwezi",
        },
        format="json",
    )

    (sent,) = [
        item for item in broadcaster.sent if item[1] is ServerEvent.RESELLER_APPLICATION_CREATED
    ]
    assert sent[0] == (STAFF,)
    assert "application_id" in sent[2]


def test_fresh_dashboard_numbers_reach_staff(broadcaster):
    container.resolve(FactsFacade).refresh()

    assert ((STAFF,), ServerEvent.DASHBOARD_UPDATED, {}) in broadcaster.sent
