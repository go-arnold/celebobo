import pytest

from apps.accounts.tests.factories import ResellerFactory, UserFactory
from apps.catalog.models import Review
from apps.orders.domain.events import AssignmentDeclined, OrderAssigned, OrderStatusChanged
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"


@pytest.fixture
def order(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])


def assign(api, order, reseller):
    return api.post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})


def move(api, order, status):
    return api.post(f"{BO}{order.pk}/transition/", {"to": status})


class TestBackofficeList:
    def test_managers_see_everything_with_counts(self, as_user, manager, order):
        body = as_user(manager).get(BO).json()

        assert body["meta"]["count"] == 1
        assert body["meta"]["counts"]["pending"] == 1
        assert body["meta"]["counts"]["unassigned"] == 1
        assert body["results"][0]["client_name"] == "Aline Mbuyi"

    def test_resellers_only_see_their_assignments(self, as_user, manager, reseller, order):
        assign(as_user(manager), order, reseller)

        mine = as_user(reseller).get(BO).json()
        other = as_user(ResellerFactory.create()).get(BO).json()

        assert mine["meta"]["count"] == 1
        assert other["meta"]["count"] == 0
        assert as_user(ResellerFactory.create()).get(f"{BO}{order.pk}/").status_code == 404

    def test_filters(self, as_user, manager, order):
        api = as_user(manager)

        assert api.get(BO, {"status": "unassigned"}).json()["meta"]["count"] == 1
        assert api.get(BO, {"search": "aline"}).json()["meta"]["count"] == 1
        assert api.get(BO, {"payment_method": "cash"}).json()["meta"]["count"] == 0
        assert api.get(BO, {"date_from": "2999-01-01"}).json()["meta"]["count"] == 0

    def test_clients_have_no_backoffice(self, as_user, shopper, order):
        assert as_user(shopper).get(BO).status_code == 403


class TestAssignment:
    def test_assigning_moves_pending_to_assigned(
        self, as_user, manager, reseller, order, published_events
    ):
        body = assign(as_user(manager), order, reseller).json()

        assert body["status"] == "assigned"
        assert body["reseller"]["name"] == "Patrick Kabasele"
        assert body["client"]["email"] == "aline@celebobo.test"
        assert published_events.single(OrderAssigned).reseller_id == reseller.pk
        assert published_events.single(OrderStatusChanged).status == "assigned"

    def test_reassignment_keeps_the_status(
        self, as_user, manager, reseller, order, published_events
    ):
        api = as_user(manager)
        assign(api, order, reseller)
        other = ResellerFactory.create()

        body = assign(api, order, other).json()

        assert body["status"] == "assigned"
        assert body["reseller"]["id"] == other.pk
        assert published_events.of_type(OrderAssigned)[-1].previous_reseller_id == reseller.pk

    def test_only_active_resellers(self, as_user, manager, order):
        response = as_user(manager).post(
            f"{BO}{order.pk}/assign/", {"reseller_id": UserFactory.create().pk}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "reseller_not_found"

    def test_resellers_cannot_assign(self, as_user, reseller, order):
        assert assign(as_user(reseller), order, reseller).status_code == 403

    def test_reseller_declines(self, as_user, manager, reseller, order, published_events):
        assign(as_user(manager), order, reseller)

        response = as_user(reseller).post(f"{BO}{order.pk}/decline/", {"reason": "Indisponible"})

        assert response.status_code == 204
        order.refresh_from_db()
        assert order.status == "pending"
        assert order.assigned_reseller is None
        assert published_events.single(AssignmentDeclined).reason == "Indisponible"

    def test_assignable_resellers_with_workload(self, as_user, manager, reseller, order):
        assign(as_user(manager), order, reseller)

        body = as_user(manager).get("/api/v1/bo/resellers/assignable/").json()

        assert body == [
            {
                "id": reseller.pk,
                "name": "Patrick Kabasele",
                "availability": "offline",
                "open_orders": 1,
            }
        ]


class TestTransitions:
    def test_reseller_walks_the_flow_one_step_at_a_time(self, as_user, manager, reseller, order):
        assign(as_user(manager), order, reseller)
        api = as_user(reseller)

        skipped = move(api, order, "delivered")
        statuses = [
            move(api, order, status).json()["status"]
            for status in ("confirmed", "paid", "shipping", "delivered")
        ]

        assert skipped.status_code == 422
        assert statuses == ["confirmed", "paid", "shipping", "delivered"]
        history = as_user(manager).get(f"{BO}{order.pk}/").json()["history"]
        assert [entry["status"] for entry in history] == [
            "pending",
            "assigned",
            "confirmed",
            "paid",
            "shipping",
            "delivered",
        ]
        assert history[2]["actor_role"] == "reseller"
        assert history[2]["actor_name"] == "Patrick Kabasele"

    def test_manager_jumps_and_returns_restock(self, as_user, manager, order, phone):
        api = as_user(manager)

        delivered = move(api, order, "delivered").json()
        returned = move(api, order, "returned").json()

        assert delivered["allowed_transitions"] == ["returned"]
        assert returned["status"] == "returned"
        phone.refresh_from_db()
        assert phone.stock == 5

    def test_delivery_unlocks_reviews(self, as_user, manager, shopper, order, phone):
        move(as_user(manager), order, "delivered")

        response = as_user(shopper).post(
            f"/api/v1/products/{phone.slug}/reviews/",
            {"rating": 5, "message": "Livré rapidement, très satisfaite."},
        )

        assert response.status_code == 201
        assert Review.objects.get().verified is True

    def test_detail_lists_allowed_transitions_per_actor(self, as_user, manager, reseller, order):
        assign(as_user(manager), order, reseller)

        assert as_user(reseller).get(f"{BO}{order.pk}/").json()["allowed_transitions"] == [
            "confirmed"
        ]
        assert as_user(manager).get(f"{BO}{order.pk}/").json()["allowed_transitions"] == [
            "confirmed",
            "paid",
            "shipping",
            "delivered",
            "cancelled",
        ]
