import pytest

from apps.accounts.tests.factories import UserFactory
from apps.orders.domain.events import ResellerRated
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"
RESELLERS = "/api/v1/bo/resellers/"


@pytest.fixture
def order(as_user, shopper, phone, place_order, *, manager, reseller) -> Order:
    order = Order.objects.get(number=place_order(shopper, phone)["number"])
    as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    return order


def deliver(as_user, manager, order) -> None:
    response = as_user(manager).post(
        f"{BO}{order.pk}/transition/", {"to": "delivered", "reason": "Remise vérifiée"}
    )
    assert response.json()["status"] == "delivered"


def rate(api, order, score, comment=""):
    return api.post(f"{MINE}{order.number}/rating/", {"score": score, "comment": comment})


class TestRating:
    def test_after_delivery_the_client_rates_the_reseller_once(
        self, as_user, shopper, manager, *, reseller, order, published_events
    ):
        before = as_user(shopper).get(f"{MINE}{order.number}/").json()
        deliver(as_user, manager, order)
        ready = as_user(shopper).get(f"{MINE}{order.number}/").json()

        rated = rate(as_user(shopper), order, 4, "  Très   aimable, livraison rapide  ")
        again = rate(as_user(shopper), order, 5)

        assert (before["can_rate"], ready["can_rate"]) == (False, True)
        assert rated.status_code == 200, rated.json()
        assert rated.json()["rating"]["score"] == 4
        assert rated.json()["rating"]["comment"] == "Très aimable, livraison rapide"
        assert rated.json()["can_rate"] is False
        assert again.json()["code"] == "already_rated"
        event = published_events.single(ResellerRated)
        assert (event.reseller_id, event.score) == (reseller.pk, 4)

    def test_not_before_delivery(self, as_user, shopper, order):
        response = rate(as_user(shopper), order, 5)

        assert response.json()["code"] == "order_not_ratable"

    def test_the_score_goes_from_one_to_five(self, as_user, shopper, manager, order):
        deliver(as_user, manager, order)

        assert rate(as_user(shopper), order, 0).status_code == 400
        assert rate(as_user(shopper), order, 6).status_code == 400

    def test_only_the_client_of_the_order(self, as_user, manager, order):
        deliver(as_user, manager, order)

        assert rate(as_user(UserFactory.create()), order, 5).status_code == 404


class TestDirectory:
    def test_the_directory_shows_average_and_count(
        self, as_user, shopper, phone, place_order, *, manager, reseller, order
    ):
        deliver(as_user, manager, order)
        rate(as_user(shopper), order, 4, "Bien")
        second = Order.objects.get(number=place_order(shopper, phone)["number"])
        as_user(manager).post(f"{BO}{second.pk}/assign/", {"reseller_id": reseller.pk})
        deliver(as_user, manager, second)
        rate(as_user(shopper), second, 5)

        row = next(
            r for r in as_user(manager).get(RESELLERS).json()["results"] if r["id"] == reseller.pk
        )
        ratings = as_user(manager).get(f"{RESELLERS}{reseller.pk}/ratings/").json()

        assert (row["rating_average"], row["rating_count"]) == ("4.5", 2)
        assert [r["score"] for r in ratings["results"]] == [5, 4]
        assert ratings["results"][1] == {
            "order_number": order.number,
            "client_name": "Aline",
            "score": 4,
            "comment": "Bien",
            "created_at": ratings["results"][1]["created_at"],
        }

    def test_a_reseller_without_ratings(self, as_user, manager, reseller):
        row = next(
            r for r in as_user(manager).get(RESELLERS).json()["results"] if r["id"] == reseller.pk
        )

        assert (row["rating_average"], row["rating_count"]) == (None, 0)
