import pytest

from apps.accounts.tests.factories import ResellerFactory, UserFactory

pytestmark = pytest.mark.django_db

DASHBOARD = "/api/v1/bo/dashboard/"


@pytest.mark.usefixtures("activity")
class TestSummary:
    def test_staff_kpis_compare_with_the_previous_period(self, as_user, manager):
        body = as_user(manager).get(f"{DASHBOARD}summary/", {"period": "7d"}).json()

        assert body["revenue"] == {"value": "210.00", "previous": "120.00", "change": 75.0}
        assert body["sales_count"] == {"value": "2.00", "previous": "1.00", "change": 100.0}
        assert body["units"]["value"] == "3.00"
        assert body["average_basket"]["value"] == "105.00"
        assert body["profit"]["value"] == "46.00"
        assert body["margin_rate"] == "21.9"
        assert body["today_revenue"] == "10.00"
        assert body["open_orders"] == 0

    def test_resellers_only_see_their_numbers(self, as_user, reseller):
        body = as_user(reseller).get(f"{DASHBOARD}summary/", {"period": "30d"}).json()

        assert body["revenue"]["value"] == "210.00"
        assert body["revenue"]["previous"] == "0.00"
        assert body["revenue"]["change"] is None

    def test_staff_filter_by_seller_and_payment(self, as_user, manager, reseller):
        api = as_user(manager)

        by_seller = api.get(f"{DASHBOARD}summary/", {"period": "30d", "seller_id": manager.pk})
        by_payment = api.get(
            f"{DASHBOARD}summary/", {"period": "30d", "payment_method": "orange_money"}
        )

        assert by_seller.json()["revenue"]["value"] == "120.00"
        assert by_payment.json()["revenue"]["value"] == "10.00"

    def test_resellers_cannot_widen_their_scope(self, as_user, reseller, manager):
        body = (
            as_user(reseller)
            .get(f"{DASHBOARD}summary/", {"period": "30d", "seller_id": manager.pk})
            .json()
        )

        assert body["revenue"]["value"] == "210.00"


@pytest.mark.usefixtures("activity")
class TestCharts:
    def test_series_fills_every_day(self, as_user, manager):
        body = as_user(manager).get(f"{DASHBOARD}revenue-series/", {"period": "7d"}).json()

        assert body["granularity"] == "day"
        assert len(body["points"]) == 7
        assert body["points"][-1]["revenue"] == "10.00"
        assert body["points"][-2]["revenue"] == "200.00"
        assert body["points"][-2]["average_basket"] == "200.00"
        assert body["points"][0]["revenue"] == "0.00"

    def test_yearly_series_is_monthly(self, as_user, manager):
        body = as_user(manager).get(f"{DASHBOARD}revenue-series/", {"period": "12m"}).json()

        assert body["granularity"] == "month"
        assert len(body["points"]) == 12
        assert sum(float(point["revenue"]) for point in body["points"]) == 330.0

    def test_payment_split(self, as_user, manager):
        body = as_user(manager).get(f"{DASHBOARD}payment-split/", {"period": "7d"}).json()

        assert body == [
            {"payment_method": "cash", "revenue": "200.00", "sales_count": 1, "share": 95.2},
            {"payment_method": "orange_money", "revenue": "10.00", "sales_count": 1, "share": 4.8},
        ]

    def test_top_products(self, as_user, manager, phone):
        api = as_user(manager)

        by_revenue = api.get(f"{DASHBOARD}top-products/", {"period": "30d"}).json()
        top_one = api.get(f"{DASHBOARD}top-products/", {"period": "30d", "limit": 1}).json()
        by_units = api.get(f"{DASHBOARD}top-products/", {"by": "units"}).json()

        assert [row["name"] for row in by_revenue] == ["Galaxy A55", "Coque"]
        assert by_revenue[0]["revenue"] == "320.00"
        assert by_revenue[0]["units"] == 3
        assert [row["product_id"] for row in top_one] == [phone.pk]
        assert by_units[0]["units"] == 3


class TestWidgets:
    @pytest.mark.usefixtures("activity")
    def test_recent_sales_are_live_and_scoped(self, as_user, manager, reseller, sell, case):
        sell(manager, case, unit_price="12.00")

        staff = as_user(manager).get(f"{DASHBOARD}recent-sales/").json()
        mine = as_user(reseller).get(f"{DASHBOARD}recent-sales/").json()

        assert len(staff) == 4
        assert staff[0]["total"] == "12.00"
        assert len(mine) == 2
        assert {row["seller_name"] for row in mine} == {"Patrick Kabasele"}

    def test_open_orders(self, as_user, manager, shopper, phone, place_order):
        place_order(shopper, phone)

        staff = as_user(manager).get(f"{DASHBOARD}open-orders/").json()
        mine = as_user(ResellerFactory.create()).get(f"{DASHBOARD}open-orders/").json()

        assert staff["count"] == 1
        assert staff["results"][0]["status"] == "pending"
        assert mine == {"count": 0, "results": []}
        summary = as_user(manager).get(f"{DASHBOARD}summary/").json()
        assert summary["open_orders"] == 1


def test_validates_filters(as_user, manager):
    response = as_user(manager).get(
        f"{DASHBOARD}summary/", {"date_from": "2026-02-01", "date_to": "2026-01-01"}
    )

    assert response.status_code == 400


def test_clients_have_no_dashboard(as_user):
    assert as_user(UserFactory.create()).get(f"{DASHBOARD}summary/").status_code == 403
