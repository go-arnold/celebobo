from decimal import Decimal

import pytest
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.domain.events import ResellerUpdated, UserActivationChanged
from apps.accounts.tests.factories import ResellerFactory, UserFactory

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/resellers/"


@pytest.fixture
def invited(reseller, shopper):
    shopper.invited_by = reseller
    shopper.save(update_fields=["invited_by"])
    return shopper


def record_sale(api, product, key, unit_price="100.00", quantity=2):
    response = api.post(
        "/api/v1/bo/sales/",
        {
            "product_id": product.pk,
            "quantity": quantity,
            "unit_price": unit_price,
            "payment_method": "cash",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 201, response.json()


class TestDirectory:
    def test_lists_resellers_with_performance(self, as_user, manager, reseller, phone):
        record_sale(as_user(reseller), phone, "sale-000001")
        UserFactory.create(invited_by=reseller)

        body = as_user(manager).get(BO).json()

        assert body["meta"]["count"] == 1
        (row,) = body["results"]
        assert row["name"] == "Patrick Kabasele"
        assert row["referral_code"] == "4821"
        assert row["commission_rate"] == "0.100"
        assert row["invited_count"] == 1
        assert row["is_active"] is True
        assert row["performance"] == {
            "sales_count": 1,
            "revenue": "200.00",
            "commission_earned": "20.00",
            "commission_due": "20.00",
        }

    def test_filters_and_ordering(self, as_user, manager, reseller):
        quiet = ResellerFactory.create(first_name="Aimé", is_active=False)
        UserFactory.create(invited_by=reseller)
        api = as_user(manager)

        assert api.get(BO, {"search": "4821"}).json()["meta"]["count"] == 1
        assert api.get(BO, {"active": "false"}).json()["results"][0]["id"] == quiet.pk
        assert [row["id"] for row in api.get(BO, {"ordering": "-invited"}).json()["results"]] == [
            reseller.pk,
            quiet.pk,
        ]
        assert [row["id"] for row in api.get(BO).json()["results"]] == [quiet.pk, reseller.pk]

    def test_stats(self, as_user, manager, reseller, phone, shopper):
        other = ResellerFactory.create()
        record_sale(as_user(reseller), phone, "sale-000001")
        record_sale(as_user(other), phone, "sale-000002", unit_price="50.00", quantity=1)
        shopper.invited_by = reseller
        shopper.save(update_fields=["invited_by"])

        body = as_user(manager).get(f"{BO}stats/").json()

        assert body["total"] == 2
        assert body["active"] == 2
        assert body["invited_clients"] == 1
        assert body["pending_applications"] == 0
        assert body["top_reseller"] == {
            "id": reseller.pk,
            "name": "Patrick Kabasele",
            "revenue": "200.00",
        }

    def test_detail_and_unknown(self, as_user, manager, reseller, shopper):
        api = as_user(manager)

        assert api.get(f"{BO}{reseller.pk}/").json()["email"] == reseller.email
        assert api.get(f"{BO}{shopper.pk}/").status_code == 404

    def test_resellers_cannot_browse_the_directory(self, as_user, reseller):
        assert as_user(reseller).get(BO).status_code == 403


class TestManagement:
    def test_updates_rate_and_manager(self, as_user, manager, reseller, published_events):
        response = as_user(manager).patch(
            f"{BO}{reseller.pk}/",
            {"commission_rate": "0.150", "manager_id": manager.pk},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["commission_rate"] == "0.150"
        assert response.json()["manager"] == {"id": manager.pk, "name": "Joël Mpiana"}
        updated = next(e for e in published_events.events if isinstance(e, ResellerUpdated))
        assert set(updated.fields) == {"commission_rate", "manager_id"}

    def test_clearing_the_manager_and_validation(self, as_user, manager, reseller, shopper):
        reseller.manager = manager
        reseller.save(update_fields=["manager"])
        api = as_user(manager)

        cleared = api.patch(f"{BO}{reseller.pk}/", {"manager_id": None}, format="json")
        bad_manager = api.patch(f"{BO}{reseller.pk}/", {"manager_id": shopper.pk}, format="json")
        bad_rate = api.patch(f"{BO}{reseller.pk}/", {"commission_rate": "0.9"}, format="json")

        assert cleared.json()["manager"] is None
        assert bad_manager.status_code == 400
        assert bad_rate.status_code == 400

    def test_deactivation_revokes_sessions(self, as_user, manager, reseller, published_events):
        RefreshToken.for_user(reseller)
        api = as_user(manager)

        response = api.post(f"{BO}{reseller.pk}/deactivate/")
        again = api.post(f"{BO}{reseller.pk}/deactivate/")

        assert response.json()["is_active"] is False
        assert again.status_code == 200
        reseller.refresh_from_db()
        assert reseller.is_active is False
        assert reseller.availability == "offline"
        assert not OutstandingToken.objects.filter(
            user=reseller, blacklistedtoken__isnull=True
        ).exists()
        changes = [e for e in published_events.events if isinstance(e, UserActivationChanged)]
        assert len(changes) == 1

    def test_reactivation(self, as_user, manager):
        dormant = ResellerFactory.create(is_active=False)

        response = as_user(manager).post(f"{BO}{dormant.pk}/activate/")

        assert response.json()["is_active"] is True

    def test_invitees_with_order_totals(self, as_user, manager, invited, phone, place_order):
        reseller_id = invited.invited_by_id
        UserFactory.create(invited_by_id=reseller_id)
        place_order(invited, phone, quantity=1)

        body = as_user(manager).get(f"{BO}{reseller_id}/invitees/").json()

        assert body["meta"]["count"] == 2
        assert body["meta"]["summary"] == {
            "code": "4821",
            "invited_count": 2,
            "orders_total": "122.98",
        }
        rows = {row["id"]: row for row in body["results"]}
        assert rows[invited.pk]["orders_count"] == 1
        assert rows[invited.pk]["orders_total"] == "122.98"

    def test_commission_changes_need_manager_rights(self, as_user, reseller):
        response = as_user(reseller).patch(
            f"{BO}{reseller.pk}/", {"commission_rate": "0.500"}, format="json"
        )

        assert response.status_code == 403
        reseller.refresh_from_db()
        assert reseller.commission_rate == Decimal("0.100")
