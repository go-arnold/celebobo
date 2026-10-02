from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory
from apps.catalog.models import Product, StockMovement
from apps.catalog.tests.factories import ProductFactory
from apps.sales.domain.events import SaleDeleted, SaleRecorded, SaleRefunded
from apps.sales.models import CommissionEntry, Sale

pytestmark = pytest.mark.django_db

SALES = "/api/v1/bo/sales/"


def stock_of(product: Product) -> int:
    product.refresh_from_db()
    return product.stock


def commission_total(reseller) -> Decimal:
    return sum(
        (entry.amount for entry in CommissionEntry.objects.filter(reseller=reseller)),
        Decimal(0),
    )


class TestRecording:
    def test_reseller_sale_moves_stock_and_earns_commission(
        self, reseller, phone, record_sale, published_events
    ):
        body = record_sale(reseller, phone)

        assert body["total"] == "200.00"
        assert body["profit"] == "40.00"
        assert body["unit_cost"] == "80.00"
        assert body["sold_to"] == "Jean Mukendi"
        assert body["seller"]["id"] == reseller.pk
        assert stock_of(phone) == 8
        phone.refresh_from_db()
        assert phone.sales_count == 2
        assert commission_total(reseller) == Decimal("20.00")
        assert StockMovement.objects.filter(product=phone, reason="sale").exists()
        assert any(isinstance(event, SaleRecorded) for event in published_events.events)

    def test_cost_is_frozen_at_sale_time(self, reseller, phone, record_sale):
        body = record_sale(reseller, phone)
        Product.objects.filter(pk=phone.pk).update(cost_price=Decimal("10.00"))

        assert Sale.objects.get(pk=body["id"]).unit_cost == Decimal("80.00")

    def test_managers_attribute_sales_to_a_reseller(self, manager, reseller, phone, record_sale):
        body = record_sale(manager, phone, seller_id=reseller.pk)

        assert body["seller"]["id"] == reseller.pk
        assert body["seller"]["name"] == "Patrick Kabasele"

    def test_manager_sales_without_seller_earn_no_commission(self, manager, phone, record_sale):
        body = record_sale(manager, phone)

        assert body["seller"]["id"] == manager.pk
        assert not CommissionEntry.objects.exists()

    def test_resellers_cannot_attribute_sales_to_others(self, reseller, phone, record_sale):
        other = ResellerFactory.create()

        body = record_sale(reseller, phone, seller_id=other.pk)

        assert body["seller"]["id"] == reseller.pk

    def test_rejects_clients_as_sellers(self, manager, shopper, phone, as_user):
        response = as_user(manager).post(
            SALES,
            {
                "product_id": phone.pk,
                "quantity": 1,
                "unit_price": "10",
                "payment_method": "cash",
                "seller_id": shopper.pk,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="sale-bad-seller",
        )

        assert response.status_code == 400
        assert "seller_id" in response.json()["errors"]

    def test_rejects_future_dates_and_overselling(self, reseller, phone, as_user):
        api = as_user(reseller)
        base = {"product_id": phone.pk, "unit_price": "10", "payment_method": "cash"}

        future = api.post(
            SALES,
            {**base, "quantity": 1, "sold_at": (timezone.now() + timedelta(days=1)).isoformat()},
            format="json",
            HTTP_IDEMPOTENCY_KEY="sale-future",
        )
        oversell = api.post(
            SALES, {**base, "quantity": 99}, format="json", HTTP_IDEMPOTENCY_KEY="sale-oversell"
        )

        assert future.status_code == 400
        assert "sold_at" in future.json()["errors"]
        assert oversell.status_code in (409, 422)
        assert not Sale.objects.exists()
        assert stock_of(phone) == 10

    def test_clients_cannot_record(self, shopper, phone, as_user):
        response = as_user(shopper).post(
            SALES, {}, format="json", HTTP_IDEMPOTENCY_KEY="key-k-1-000000"
        )

        assert response.status_code == 403

    def test_bulk_is_atomic_and_reports_the_failing_line(self, reseller, phone, as_user):
        line = {"product_id": phone.pk, "quantity": 1, "unit_price": "50", "payment_method": "cash"}
        api = as_user(reseller)

        ok = api.post(
            f"{SALES}bulk/",
            {"lines": [line, line]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-bulk-1-000000",
        )
        failed = api.post(
            f"{SALES}bulk/",
            {"lines": [line, {**line, "quantity": 500}]},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-bulk-2-000000",
        )

        assert ok.status_code == 201
        assert len(ok.json()) == 2
        assert failed.status_code == 400
        assert failed.json()["meta"]["line"] == 2
        assert Sale.objects.count() == 2
        assert stock_of(phone) == 8


class TestListing:
    def test_stats_and_scoping(self, as_user, manager, reseller, phone, record_sale):
        other = ResellerFactory.create()
        record_sale(reseller, phone)
        record_sale(other, phone, quantity=1, unit_price="120.00")

        everything = as_user(manager).get(SALES).json()
        mine = as_user(reseller).get(SALES).json()

        assert everything["meta"]["count"] == 2
        assert everything["meta"]["stats"] == {
            "revenue": "320.00",
            "profit": "80.00",
            "count": 2,
            "units": 3,
            "average": "160.00",
        }
        assert mine["meta"]["count"] == 1
        assert mine["meta"]["stats"]["revenue"] == "200.00"

    def test_filters(self, as_user, manager, reseller, phone, record_sale):
        record_sale(reseller, phone)
        api = as_user(manager)

        assert api.get(SALES, {"search": "mukendi"}).json()["meta"]["count"] == 1
        assert api.get(SALES, {"payment_method": "orange_money"}).json()["meta"]["count"] == 0
        assert api.get(SALES, {"seller_id": reseller.pk}).json()["meta"]["count"] == 1
        assert api.get(SALES, {"period": "7d"}).json()["meta"]["count"] == 1
        assert api.get(SALES, {"date_from": "2999-01-01"}).json()["meta"]["count"] == 0
        assert api.get(SALES, {"status": "refunded"}).json()["meta"]["count"] == 0
        assert (
            api.get(SALES, {"date_from": "2026-02-01", "date_to": "2026-01-01"}).status_code == 400
        )

    def test_other_resellers_cannot_see_a_sale(self, as_user, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        assert as_user(ResellerFactory.create()).get(f"{SALES}{sale['id']}/").status_code == 404
        assert as_user(reseller).get(f"{SALES}{sale['id']}/").status_code == 200


class TestEditing:
    def test_price_change_rebases_commission(self, as_user, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        response = as_user(reseller).patch(
            f"{SALES}{sale['id']}/", {"unit_price": "150.00"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["total"] == "300.00"
        assert commission_total(reseller) == Decimal("30.00")

    def test_other_fields_leave_commission_untouched(self, as_user, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        response = as_user(reseller).patch(
            f"{SALES}{sale['id']}/",
            {"sold_to": "Marie", "payment_method": "airtel_money"},
            format="json",
        )

        assert response.json()["sold_to"] == "Marie"
        assert CommissionEntry.objects.count() == 1

    def test_refunded_sales_cannot_be_edited(self, as_user, manager, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)
        as_user(manager).post(
            f"{SALES}{sale['id']}/refund/",
            {"kind": "refund", "amount": "10"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-r-1-000000",
        )

        response = as_user(manager).patch(f"{SALES}{sale['id']}/", {"sold_to": "X"}, format="json")

        assert response.status_code == 422


class TestRefunds:
    def refund(self, api, sale, key, **payload):
        return api.post(
            f"{SALES}{sale['id']}/refund/", payload, format="json", HTTP_IDEMPOTENCY_KEY=key
        )

    def test_partial_refunds_reverse_commission_proportionally(
        self, as_user, manager, reseller, record_sale, published_events
    ):
        sale = record_sale(reseller)
        api = as_user(manager)

        first = self.refund(
            api, sale, "key-r-1-000000", kind="refund", amount="50.00", reason="Rayure"
        )
        too_much = self.refund(api, sale, "key-r-2-000000", kind="refund", amount="151.00")

        assert first.status_code == 200
        body = first.json()
        assert body["status"] == "refunded"
        assert body["refunded_amount"] == "50.00"
        assert body["profit"] == "-10.00"
        assert body["refunds"][0]["reason"] == "Rayure"
        assert commission_total(reseller) == Decimal("15.00")
        assert too_much.status_code == 400
        assert too_much.json()["meta"]["refundable"] == "150.00"
        assert any(isinstance(event, SaleRefunded) for event in published_events.events)

    def test_returns_restock_and_void_remaining_commission(
        self, as_user, manager, reseller, phone, record_sale
    ):
        sale = record_sale(reseller, phone)
        api = as_user(manager)
        self.refund(api, sale, "key-r-1-000000", kind="refund", amount="50.00")

        returned = self.refund(api, sale, "key-r-2-000000", kind="return", reason="Défectueux")
        again = self.refund(api, sale, "key-r-3-000000", kind="refund", amount="1")

        assert returned.json()["status"] == "returned"
        assert returned.json()["refunded_amount"] == "200.00"
        assert stock_of(phone) == 10
        assert commission_total(reseller) == Decimal("0.00")
        assert again.status_code == 422
        stats = api.get(SALES).json()["meta"]["stats"]
        assert stats["revenue"] == "0.00"
        assert stats["count"] == 0

    def test_resellers_cannot_refund(self, as_user, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        assert (
            self.refund(as_user(reseller), sale, "key-r-1-000000", kind="return").status_code == 403
        )


class TestDeletion:
    def test_admins_delete_restock_and_void(self, as_user, admin, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        response = as_user(admin).delete(f"{SALES}{sale['id']}/")

        assert response.status_code == 204
        assert not Sale.objects.exists()
        assert stock_of(phone) == 10
        phone.refresh_from_db()
        assert phone.sales_count == 0
        assert commission_total(reseller) == Decimal("0.00")
        assert CommissionEntry.objects.filter(sale__isnull=True).count() == 2

    def test_deletion_is_published(self, as_user, admin, reseller, record_sale, published_events):
        sale = record_sale(reseller)

        as_user(admin).delete(f"{SALES}{sale['id']}/")

        assert any(isinstance(event, SaleDeleted) for event in published_events.events)

    def test_deleting_a_returned_sale_does_not_restock_twice(
        self, as_user, admin, reseller, phone, record_sale
    ):
        sale = record_sale(reseller, phone)
        api = as_user(admin)
        api.post(
            f"{SALES}{sale['id']}/refund/",
            {"kind": "return"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-r-1-000000",
        )

        api.delete(f"{SALES}{sale['id']}/")

        assert stock_of(phone) == 10

    def test_managers_cannot_delete(self, as_user, reseller, phone, record_sale):
        sale = record_sale(reseller, phone)

        assert as_user(ManagerFactory.create()).delete(f"{SALES}{sale['id']}/").status_code == 403


def test_products_without_cost_have_no_profit(reseller, record_sale):
    product = ProductFactory.create(cost_price=None)

    body = record_sale(reseller, product)

    assert body["profit"] is None
