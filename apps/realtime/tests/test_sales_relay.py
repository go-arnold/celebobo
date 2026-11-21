from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminFactory, ResellerFactory
from apps.analytics.facades import FactsFacade
from apps.catalog.tests.factories import ProductFactory
from apps.realtime.domain.groups import STAFF, user_group
from apps.realtime.domain.protocol import ServerEvent
from apps.realtime.tests.test_presence_api import authenticated, broadcaster
from apps.sales.domain.payouts import PayoutCalendar
from apps.sales.facades import CommissionFacade
from apps.sales.models import PayoutStatement
from core.container import container

__all__ = ["broadcaster"]

pytestmark = pytest.mark.django_db(transaction=True)


def test_sales_commissions_and_payouts_are_pushed(broadcaster):
    reseller = ResellerFactory.create()
    product = ProductFactory.create(stock=5)

    authenticated(reseller).post(
        "/api/v1/bo/sales/",
        {
            "product_id": product.pk,
            "quantity": 1,
            "unit_price": "100",
            "payment_method": "cash",
            "sold_at": (timezone.now() - timedelta(days=10)).isoformat(),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="relay-sale-0001",
    )
    container.resolve(CommissionFacade).prepare_statements(
        PayoutCalendar().next(timezone.localdate())
    )
    authenticated(AdminFactory.create()).post(
        "/api/v1/bo/payouts/",
        {"statement_id": PayoutStatement.objects.get(reseller=reseller).pk},
        format="json",
        HTTP_IDEMPOTENCY_KEY="relay-payout-01",
    )

    sent: dict[ServerEvent, tuple[Any, Any]] = {}
    for groups, event, data in broadcaster.sent:
        sent.setdefault(event, (groups, data))
    groups, data = sent[ServerEvent.SALE_CREATED]
    assert set(groups) == {user_group(reseller.pk), STAFF}
    assert data["total"] == "100.00"
    assert sent[ServerEvent.COMMISSION_UPDATED] == (
        (user_group(reseller.pk),),
        {"reseller_id": reseller.pk, "delta": "10.00"},
    )
    assert sent[ServerEvent.PAYOUT_CREATED][1]["amount"] == "10.00"
    statement_pushes = [data for _, event, data in broadcaster.sent if "statement_id" in data]
    assert statement_pushes[0]["reseller_id"] == reseller.pk


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


def test_finished_jobs_reach_their_owner(broadcaster):
    owner = ResellerFactory.create()

    authenticated(owner).post("/api/v1/bo/sales/export/", {"format": "csv"}, format="json")

    (sent,) = [item for item in broadcaster.sent if item[1] is ServerEvent.JOB_COMPLETED]
    assert sent[0] == (user_group(owner.pk),)
    assert sent[2]["status"] == "done"
    assert sent[2]["kind"] == "sales_export"


def test_contact_messages_reach_staff(broadcaster):
    APIClient().post(
        "/api/v1/contact/",
        {
            "name": "Aline",
            "email": "aline@example.com",
            "subject": "other",
            "message": "Bonjour, une question rapide.",
        },
        format="json",
    )

    created = ServerEvent.CONTACT_MESSAGE_CREATED
    (sent,) = [item for item in broadcaster.sent if item[1] is created]
    assert sent[0] == (STAFF,)
