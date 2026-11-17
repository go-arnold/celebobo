import pytest

from apps.accounts.models import User
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"


@pytest.fixture
def placed(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone)["number"])


@pytest.fixture
def order(as_user, manager, reseller, placed: Order, django_capture_on_commit_callbacks) -> Order:
    # the reseller joins the order thread in an after-commit handler
    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).post(f"{BO}{placed.pk}/assign/", {"reseller_id": reseller.pk})
    return placed


class TestOrderDetail:
    def test_resellers_do_not_get_the_client_email(self, as_user, reseller, order):
        client = as_user(reseller).get(f"{BO}{order.pk}/").json()["client"]

        assert client["email"] is None
        assert client["name"] == "Aline Mbuyi"
        assert client["phone"] == "+243 81 000 0001"

    def test_staff_still_see_it(self, as_user, manager, order):
        staff_view = as_user(manager).get(f"{BO}{order.pk}/").json()["client"]

        assert staff_view["email"] == "aline@celebobo.test"

    def test_a_nameless_client_shows_the_recipient_to_resellers(
        self, as_user, manager, reseller, order
    ):
        User.objects.filter(pk=order.client_id).update(first_name="", last_name="")

        reseller_view = as_user(reseller).get(f"{BO}{order.pk}/").json()
        listed = as_user(reseller).get(BO).json()["results"][0]
        staff_view = as_user(manager).get(f"{BO}{order.pk}/").json()

        assert reseller_view["client"]["name"] == "Aline Mbuyi"
        assert listed["client_name"] == "Aline Mbuyi"
        assert staff_view["client"]["name"] == "aline@celebobo.test"


class TestSearch:
    def test_resellers_cannot_search_orders_by_client_email(
        self, as_user, manager, reseller, order
    ):
        by_email = as_user(reseller).get(BO, {"search": "aline@celebobo"}).json()
        by_name = as_user(reseller).get(BO, {"search": "Mbuyi"}).json()
        staff = as_user(manager).get(BO, {"search": "aline@celebobo"}).json()

        assert by_email["meta"]["count"] == 0
        assert by_name["meta"]["count"] == 1
        assert staff["meta"]["count"] == 1

    def test_resellers_cannot_search_conversations_by_client_email(
        self, as_user, manager, reseller, order
    ):
        def found(user, term):
            return as_user(user).get("/api/v1/conversations/", {"search": term}).json()

        assert found(reseller, "aline@celebobo")["meta"]["count"] == 0
        assert found(reseller, order.number)["meta"]["count"] == 1
        assert found(manager, "aline@celebobo")["meta"]["count"] == 1
