from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.loyalty.domain.events import MembershipEnding, MembershipRequested, MembershipStarted
from apps.loyalty.facades import MembershipFacade
from apps.loyalty.models import LoyaltySettings, Membership
from core.container import container

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/membership/"
REQUESTS = "/api/v1/bo/membership/requests/"


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def enabled():
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"membership_enabled": True})


@pytest.fixture
def client_user():
    return UserFactory.create(phone_number="+243 81 000 0001")


@pytest.fixture
def staff():
    return as_api(ManagerFactory.create())


def subscribe(user, plan="monthly"):
    return as_api(user).post(
        f"{MINE}requests/", {"plan": plan, "payment_method": "orange_money"}, format="json"
    )


def test_closed_programme_offers_nothing(client_user):
    api = as_api(client_user)

    assert api.get(MINE).json() == {
        "status": "none",
        "plan": None,
        "ends_at": None,
        "trial_available": False,
        "pending_request": None,
    }
    assert api.post(f"{MINE}trial/").json()["code"] == "membership_closed"
    assert subscribe(client_user).json()["code"] == "membership_closed"


class TestTrial:
    def test_starts_once_for_thirty_days(self, enabled, client_user, published_events):
        api = as_api(client_user)

        started = api.post(f"{MINE}trial/").json()
        again = api.post(f"{MINE}trial/")

        assert started["status"] == "trial"
        assert started["trial_available"] is False
        ends_at = Membership.objects.get().ends_at
        assert timedelta(days=29) < ends_at - timezone.now() <= timedelta(days=30)
        assert again.json()["meta"]["reason"] == "trial_used"
        assert published_events.single(MembershipStarted).plan == "trial"

    @pytest.mark.parametrize(
        ("fields", "reason"),
        [({"verified": False}, "email_unverified"), ({"phone_number": None}, "phone_missing")],
    )
    def test_needs_a_verified_email_and_a_phone(self, enabled, fields, reason):
        user = UserFactory.create(**{"phone_number": "+243 81 000 0002", **fields})

        response = as_api(user).post(f"{MINE}trial/")

        assert response.status_code == 422
        assert response.json()["meta"]["reason"] == reason

    def test_one_trial_per_phone_number(self, enabled, client_user):
        as_api(client_user).post(f"{MINE}trial/")
        client_user.phone_number = "+243 81 999 9999"
        client_user.save()
        other = UserFactory.create(phone_number="+243 81 000 0001")

        response = as_api(other).post(f"{MINE}trial/")

        assert response.json()["meta"]["reason"] == "phone_used"


class TestPaidPlans:
    def test_staff_confirms_the_payment(self, enabled, client_user, staff, published_events):
        pending = subscribe(client_user, "yearly").json()["pending_request"]

        listed = staff.get(REQUESTS, {"status": "pending"}).json()["results"]
        assert staff.post(f"{REQUESTS}{pending['id']}/confirm/").status_code == 204
        mine = as_api(client_user).get(MINE).json()

        assert pending["price"] == "49.00"
        assert listed[0]["member"]["email"] == client_user.email
        assert published_events.single(MembershipRequested).plan == "yearly"
        assert mine["status"] == "active"
        assert mine["plan"] == "yearly"
        assert mine["pending_request"] is None
        assert staff.post(f"{REQUESTS}{pending['id']}/confirm/").status_code == 409

    def test_a_paid_period_starts_after_the_trial(self, enabled, client_user, staff):
        as_api(client_user).post(f"{MINE}trial/")
        trial_end = Membership.objects.get().ends_at
        request_id = subscribe(client_user).json()["pending_request"]["id"]

        staff.post(f"{REQUESTS}{request_id}/confirm/")

        ends_at = Membership.objects.get().ends_at
        assert timedelta(days=28) <= ends_at - trial_end <= timedelta(days=31)

    def test_one_pending_request_at_a_time(self, enabled, client_user):
        subscribe(client_user)

        assert subscribe(client_user).json()["code"] == "membership_request_pending"

    def test_reject_and_cancel(self, enabled, client_user, staff):
        rejected = subscribe(client_user).json()["pending_request"]["id"]
        staff.post(f"{REQUESTS}{rejected}/reject/", {"note": "Paiement non reçu"}, format="json")
        cancelled = subscribe(client_user).json()["pending_request"]["id"]
        stranger = as_api(UserFactory.create()).post(f"{MINE}requests/{cancelled}/cancel/")
        mine = as_api(client_user).post(f"{MINE}requests/{cancelled}/cancel/").json()

        statuses = {row["id"]: row["status"] for row in staff.get(REQUESTS).json()["results"]}
        assert statuses == {rejected: "rejected", cancelled: "cancelled"}
        assert stranger.status_code == 404
        assert mine["pending_request"] is None

    def test_members_list(self, enabled, client_user, staff):
        as_api(client_user).post(f"{MINE}trial/")

        trials = staff.get("/api/v1/bo/memberships/", {"status": "trial"}).json()["results"]
        active = staff.get("/api/v1/bo/memberships/", {"status": "active"}).json()["results"]

        assert [row["member"]["id"] for row in trials] == [client_user.pk]
        assert active == []

    def test_resellers_cannot_confirm(self, enabled):
        assert as_api(ResellerFactory.create()).get(REQUESTS).status_code == 403


class TestFreeDelivery:
    def quote(self, user, city):
        product = ProductFactory.create(price=Decimal("20.00"))
        return (
            as_api(user)
            .post(
                "/api/v1/checkout/quote/",
                {"lines": [{"product_id": product.pk, "quantity": 1}], "city": city},
                format="json",
            )
            .json()
        )

    def test_members_ship_for_free_in_member_zones(self, enabled, client_user):
        as_api(client_user).post(f"{MINE}trial/")

        bukavu = self.quote(client_user, "Bukavu")
        elsewhere = self.quote(client_user, "Kinshasa")

        assert (bukavu["shipping_fee"], bukavu["member_free_shipping"]) == ("0.00", True)
        assert elsewhere["member_free_shipping"] is False
        assert elsewhere["shipping_fee"] != "0.00"

    def test_others_pay_the_zone_fee(self, client_user):
        quote = self.quote(client_user, "Bukavu")

        assert (quote["shipping_fee"], quote["member_free_shipping"]) == ("2.98", False)


def test_reminds_once_before_the_end(enabled, client_user, published_events):
    Membership.objects.create(
        user=client_user, plan="monthly", ends_at=timezone.now() + timedelta(days=2)
    )
    facade = container.resolve(MembershipFacade)

    assert facade.remind() == 1
    assert facade.remind() == 0
    assert published_events.single(MembershipEnding).user_id == client_user.pk
