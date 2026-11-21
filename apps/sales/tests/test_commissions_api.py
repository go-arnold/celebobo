import pytest
from django.utils import timezone

from apps.accounts.tests.factories import ResellerFactory
from apps.sales.domain.payouts import PayoutCalendar

pytestmark = pytest.mark.django_db

COMMISSIONS = "/api/v1/bo/commissions/"
PAYOUTS = "/api/v1/bo/payouts/"


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
        # pending through the 7-day trial period: nothing is payable yet
        assert body["pending"] == "20.00"
        assert body["validated"] == "0.00"
        assert body["delivery_fees"] == "0.00"
        assert body["due"] == "0.00"
        assert body["next_payout_date"] == PayoutCalendar().next(timezone.localdate()).isoformat()
        assert body["payout_threshold"] == "5.00"

    def test_resellers_cannot_peek_at_others(self, as_user, earned):
        other = ResellerFactory.create()

        body = as_user(other).get(f"{COMMISSIONS}summary/", {"reseller_id": earned.pk}).json()

        assert body["reseller"]["id"] == other.pk
        assert body["pending"] == "0.00"

    def test_staff_must_choose_a_reseller(self, as_user, manager, shopper, earned):
        api = as_user(manager)

        assert api.get(f"{COMMISSIONS}summary/").status_code == 400
        assert api.get(f"{COMMISSIONS}summary/", {"reseller_id": shopper.pk}).status_code == 400
        assert (
            api.get(f"{COMMISSIONS}summary/", {"reseller_id": earned.pk}).json()["pending"]
            == "20.00"
        )

    def test_entries_series_and_overview(self, as_user, manager, earned):
        api = as_user(earned)

        entries = api.get(COMMISSIONS).json()
        series = api.get(f"{COMMISSIONS}series/").json()
        overview = as_user(manager).get(f"{COMMISSIONS}overview/").json()

        assert entries["meta"]["count"] == 1
        assert entries["results"][0]["kind"] == "earned"
        assert entries["results"][0]["base_amount"] == "200.00"
        assert entries["results"][0]["status"] == "pending"
        assert len(series) == 6
        assert series[-1]["earned"] == "20.00"
        assert [row["reseller"]["id"] for row in overview] == [earned.pk]
        assert as_user(earned).get(f"{COMMISSIONS}overview/").status_code == 403

    def test_clients_have_no_commissions(self, as_user, shopper):
        assert as_user(shopper).get(f"{COMMISSIONS}summary/").status_code == 403
