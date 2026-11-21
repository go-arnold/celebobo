from datetime import datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"


def invite(client: User, inviter: User, at: datetime | None = None) -> None:
    client.invited_by = inviter
    client.invited_at = at or timezone.now()
    client.save(update_fields=["invited_by", "invited_at"])


@pytest.fixture
def order(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone)["number"])


def suggestion_in_detail(api, order):
    return api.get(f"{BO}{order.pk}/").json()["suggested_reseller"]


def suggestion_in_list(api):
    return api.get(BO).json()["results"][0]["suggested_reseller"]


class TestSuggestedReseller:
    def test_staff_see_the_active_reseller_who_invited_the_client(
        self, as_user, manager, reseller, shopper, order
    ):
        # no time limit, unlike referral points
        invited_at = timezone.now() - timedelta(days=3 * 365)
        invite(shopper, reseller, invited_at)
        api = as_user(manager)

        for suggestion in (suggestion_in_detail(api, order), suggestion_in_list(api)):
            assert suggestion["id"] == reseller.pk
            assert suggestion["name"] == "Patrick Kabasele"
            assert suggestion["reason"] == "invited_client"
            assert datetime.fromisoformat(suggestion["invited_at"]) == invited_at

    def test_admins_see_it_too(self, as_user, reseller, shopper, order):
        invite(shopper, reseller)
        admin = UserFactory.create(role="admin", is_staff=True)

        assert suggestion_in_detail(as_user(admin), order)["id"] == reseller.pk

    def test_a_client_who_was_not_invited_has_no_suggestion(self, as_user, manager, order):
        api = as_user(manager)

        assert suggestion_in_detail(api, order) is None
        assert suggestion_in_list(api) is None

    def test_an_inactive_reseller_is_not_suggested(
        self, as_user, manager, reseller, shopper, order
    ):
        invite(shopper, reseller)
        reseller.is_active = False
        reseller.save(update_fields=["is_active"])
        api = as_user(manager)

        assert suggestion_in_detail(api, order) is None
        assert suggestion_in_list(api) is None

    def test_an_inviter_who_is_not_a_reseller_is_not_suggested(
        self, as_user, manager, shopper, order
    ):
        invite(shopper, UserFactory.create())
        api = as_user(manager)

        assert suggestion_in_detail(api, order) is None
        assert suggestion_in_list(api) is None

    def test_the_suggestion_follows_the_client_after_assignment(
        self, as_user, manager, reseller, shopper, order
    ):
        invite(shopper, reseller)
        other = ResellerFactory.create()

        body = as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": other.pk}).json()

        assert body["reseller"]["id"] == other.pk
        assert body["suggested_reseller"]["id"] == reseller.pk

    def test_no_suggestion_once_the_inviter_is_assigned(
        self, as_user, manager, reseller, shopper, order
    ):
        invite(shopper, reseller)

        body = as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk}).json()

        assert body["suggested_reseller"] is None
        assert suggestion_in_list(as_user(manager)) is None


class TestSuggestionPrivacy:
    def test_resellers_never_get_it(self, as_user, manager, reseller, shopper, order):
        invite(shopper, reseller)
        as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
        api = as_user(reseller)

        assert suggestion_in_detail(api, order) is None
        assert suggestion_in_list(api) is None

    def test_clients_never_get_it(self, as_user, reseller, shopper, order):
        invite(shopper, reseller)
        api = as_user(shopper)

        assert "suggested_reseller" not in api.get(f"{MINE}{order.number}/").json()
        assert "suggested_reseller" not in api.get(MINE).json()["results"][0]


class TestSuggestionQueries:
    def test_the_list_looks_up_inviters_once_per_page(self, as_user, phone, place_order):
        manager = ManagerFactory.create()

        def page_queries() -> int:
            api = as_user(manager)
            with CaptureQueriesContext(connection) as queries:
                assert api.get(BO).status_code == 200
            return len(queries)

        def client_invited_by_a_new_reseller() -> None:
            client = UserFactory.create()
            invite(client, ResellerFactory.create())
            place_order(client, phone)

        client_invited_by_a_new_reseller()
        one = page_queries()
        for _ in range(3):
            client_invited_by_a_new_reseller()
        many = page_queries()

        assert many == one
