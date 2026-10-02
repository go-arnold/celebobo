from decimal import Decimal

import pytest

from apps.accounts.tests.factories import ResellerFactory
from apps.sales.domain.events import PayoutRecorded
from apps.sales.models import Payout

pytestmark = pytest.mark.django_db

COMMISSIONS = "/api/v1/bo/commissions/"
PAYOUTS = "/api/v1/bo/payouts/"


def pay(api, reseller, amount, key="payout-000001"):
    return api.post(
        PAYOUTS,
        {"reseller_id": reseller.pk, "amount": amount, "note": "Mobile money"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


@pytest.fixture
def earned(reseller, phone, record_sale):
    record_sale(reseller, phone)
    return reseller


class TestSummary:
    def test_resellers_see_their_own_balance(self, as_user, earned):
        body = as_user(earned).get(f"{COMMISSIONS}summary/").json()

        assert body["reseller"]["id"] == earned.pk
        assert body["rate"] == "0.100"
        assert body["earned_this_month"] == "20.00"
        assert body["earned_total"] == "20.00"
        assert body["paid_total"] == "0.00"
        assert body["due"] == "20.00"

    def test_resellers_cannot_peek_at_others(self, as_user, earned):
        other = ResellerFactory.create()

        body = as_user(other).get(f"{COMMISSIONS}summary/", {"reseller_id": earned.pk}).json()

        assert body["reseller"]["id"] == other.pk
        assert body["due"] == "0.00"

    def test_staff_must_choose_a_reseller(self, as_user, manager, shopper, earned):
        api = as_user(manager)

        assert api.get(f"{COMMISSIONS}summary/").status_code == 400
        assert api.get(f"{COMMISSIONS}summary/", {"reseller_id": shopper.pk}).status_code == 400
        assert (
            api.get(f"{COMMISSIONS}summary/", {"reseller_id": earned.pk}).json()["due"] == "20.00"
        )

    def test_entries_series_and_overview(self, as_user, manager, earned):
        api = as_user(earned)

        entries = api.get(COMMISSIONS).json()
        series = api.get(f"{COMMISSIONS}series/").json()
        overview = as_user(manager).get(f"{COMMISSIONS}overview/").json()

        assert entries["meta"]["count"] == 1
        assert entries["results"][0]["kind"] == "earned"
        assert entries["results"][0]["base_amount"] == "200.00"
        assert len(series) == 6
        assert series[-1]["earned"] == "20.00"
        assert [row["reseller"]["id"] for row in overview] == [earned.pk]
        assert as_user(earned).get(f"{COMMISSIONS}overview/").status_code == 403

    def test_clients_have_no_commissions(self, as_user, shopper):
        assert as_user(shopper).get(f"{COMMISSIONS}summary/").status_code == 403


class TestPayouts:
    def test_admins_pay_up_to_the_balance(self, as_user, admin, earned, published_events):
        api = as_user(admin)

        paid = pay(api, earned, "15.00")
        too_much = pay(api, earned, "5.01", key="payout-000002")

        assert paid.status_code == 201
        assert paid.json()["paid_by"]["id"] == admin.pk
        assert too_much.status_code == 400
        assert too_much.json()["meta"]["due"] == "5.00"
        summary = api.get(f"{COMMISSIONS}summary/", {"reseller_id": earned.pk}).json()
        assert summary["paid_total"] == "15.00"
        assert summary["due"] == "5.00"
        assert any(isinstance(event, PayoutRecorded) for event in published_events.events)

    def test_payouts_go_to_resellers_only(self, as_user, admin, shopper):
        assert pay(as_user(admin), shopper, "1.00").status_code == 400

    def test_listing_is_scoped(self, as_user, admin, earned):
        pay(as_user(admin), earned, "10.00")
        other = ResellerFactory.create()

        assert as_user(earned).get(PAYOUTS).json()["meta"]["count"] == 1
        assert as_user(other).get(PAYOUTS, {"reseller_id": earned.pk}).json()["meta"]["count"] == 0
        assert as_user(admin).get(PAYOUTS).json()["meta"]["count"] == 1
        assert Payout.objects.get().amount == Decimal("10.00")

    def test_managers_and_resellers_cannot_pay(self, as_user, manager, earned):
        assert pay(as_user(manager), earned, "1.00").status_code == 403
        assert pay(as_user(earned), earned, "1.00").status_code == 403
