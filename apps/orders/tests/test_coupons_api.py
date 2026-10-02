from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.orders.models import Coupon, CouponRedemption, Order
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db

COUPONS = "/api/v1/bo/coupons/"
CART_COUPON = "/api/v1/cart/coupon/"


def coupon(**fields) -> Coupon:
    defaults = {"code": "BIENVENUE10", "kind": "percent", "value": Decimal(10)}
    return Coupon.objects.create(**{**defaults, **fields})


def fill_cart(api, product, quantity=1):
    api.post("/api/v1/cart/items/", {"product_id": product.pk, "quantity": quantity}, format="json")


def checkout(api, product, key, **extra):
    return api.post(
        "/api/v1/orders/",
        {
            "lines": [{"product_id": product.pk, "quantity": 1}],
            "payment_method": "cash",
            "address": ADDRESS,
            **extra,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


class TestCart:
    def test_applying_a_coupon_discounts_the_cart(self, as_user, shopper, phone):
        coupon()
        api = as_user(shopper)
        fill_cart(api, phone)

        body = api.post(CART_COUPON, {"code": "bienvenue10"}, format="json").json()

        assert body["quote"]["coupon_code"] == "BIENVENUE10"
        assert body["quote"]["discount"] == "12.00"
        assert body["quote"]["total"] == "110.98"
        assert api.get("/api/v1/cart/").json()["quote"]["discount"] == "12.00"
        removed = api.delete(CART_COUPON).json()
        assert removed["quote"]["coupon_code"] is None

    @pytest.mark.parametrize(
        ("fields", "reason"),
        [
            ({"is_active": False}, "inactive"),
            ({"ends_at": timezone.now() - timedelta(days=1)}, "expired"),
            ({"starts_at": timezone.now() + timedelta(days=1)}, "not_started"),
            ({"min_subtotal": Decimal("500")}, "minimum"),
        ],
    )
    def test_invalid_coupons_are_refused(self, as_user, shopper, phone, fields, reason):
        coupon(**fields)
        api = as_user(shopper)
        fill_cart(api, phone)

        response = api.post(CART_COUPON, {"code": "BIENVENUE10"}, format="json")

        assert response.status_code == 400
        assert response.json()["meta"]["reason"] == reason
        assert "coupon_code" in response.json()["errors"]

    def test_unknown_and_empty_cart(self, as_user, shopper, phone):
        api = as_user(shopper)

        assert api.post(CART_COUPON, {"code": "NOPE"}, format="json").status_code == 400
        fill_cart(api, phone)
        assert (
            api.post(CART_COUPON, {"code": "NOPE"}, format="json").json()["meta"]["reason"]
            == "unknown"
        )

    def test_per_user_coupons_need_an_account(self, api, phone):
        coupon(per_user_limit=1)
        response = api.post(
            "/api/v1/cart/items/", {"product_id": phone.pk, "quantity": 1}, format="json"
        )
        token = response.json()["token"]

        refused = api.post(
            CART_COUPON, {"code": "BIENVENUE10"}, format="json", HTTP_X_CART_TOKEN=token
        )

        assert refused.json()["meta"]["reason"] == "login_required"

    def test_a_coupon_that_stops_qualifying_is_reported(self, as_user, shopper, phone):
        promo = coupon(min_subtotal=Decimal("100"))
        api = as_user(shopper)
        fill_cart(api, phone)
        api.post(CART_COUPON, {"code": "BIENVENUE10"}, format="json")
        Coupon.objects.filter(pk=promo.pk).update(min_subtotal=Decimal("1000"))

        quote = api.get("/api/v1/cart/").json()["quote"]

        assert quote["discount"] == "0.00"
        assert quote["coupon_code"] is None
        assert "minimum" in quote["coupon_error"]


class TestCheckout:
    def test_orders_record_the_discount_and_redemption(self, as_user, shopper, phone):
        promo = coupon(kind="fixed", value=Decimal("20"), free_shipping=True)

        body = checkout(as_user(shopper), phone, "coupon-000001", coupon_code="bienvenue10").json()

        order = Order.objects.get(number=body["number"])
        assert (order.subtotal, order.discount, order.shipping_fee, order.total) == (
            Decimal("120.00"),
            Decimal("20.00"),
            Decimal("0.00"),
            Decimal("100.00"),
        )
        assert order.coupon_code == "BIENVENUE10"
        assert body["discount"] == "20.00"
        assert CouponRedemption.objects.get().coupon_id == promo.pk

    def test_usage_limits(self, as_user, shopper, phone):
        coupon(usage_limit=1)
        other = UserFactory.create()
        checkout(as_user(shopper), phone, "coupon-000001", coupon_code="BIENVENUE10")

        refused = checkout(as_user(other), phone, "coupon-000002", coupon_code="BIENVENUE10")

        assert refused.status_code == 400
        assert refused.json()["meta"]["reason"] == "exhausted"
        assert Order.objects.count() == 1

    def test_per_user_limit_and_cancellation(self, as_user, shopper, phone):
        coupon(per_user_limit=1)
        api = as_user(shopper)
        first = checkout(api, phone, "coupon-000001", coupon_code="BIENVENUE10").json()

        again = checkout(api, phone, "coupon-000002", coupon_code="BIENVENUE10")
        api.post(
            f"/api/v1/me/orders/{first['number']}/cancel/",
            {"reason": "changed_mind"},
            format="json",
        )
        after_cancel = checkout(api, phone, "coupon-000003", coupon_code="BIENVENUE10")

        assert again.json()["meta"]["reason"] == "already_used"
        assert after_cancel.status_code == 201

    def test_checkout_clears_nothing_when_the_coupon_is_refused(self, as_user, shopper, phone):
        coupon(is_active=False)

        response = checkout(as_user(shopper), phone, "coupon-000001", coupon_code="BIENVENUE10")

        assert response.status_code == 400
        assert not Order.objects.exists()

    def test_quotes_report_coupon_problems_softly(self, api, phone):
        body = api.post(
            "/api/v1/checkout/quote/",
            {"lines": [{"product_id": phone.pk, "quantity": 1}], "coupon_code": "NOPE"},
            format="json",
        ).json()

        assert body["coupon_error"] == "Ce code promo n'existe pas."
        assert body["discount"] == "0.00"


class TestBackoffice:
    def test_coupon_management_and_usage(self, as_user, manager, shopper, phone):
        staff = as_user(manager)
        created = staff.post(
            COUPONS,
            {"code": "soldes", "kind": "percent", "value": "15", "max_discount": "30"},
            format="json",
        )
        checkout(as_user(shopper), phone, "coupon-000001", coupon_code="SOLDES")
        staff = as_user(manager)

        detail = staff.get(f"{COUPONS}{created.json()['id']}/").json()
        duplicate = staff.post(
            COUPONS, {"code": "SOLDES", "kind": "fixed", "value": "5"}, format="json"
        )
        too_much = staff.post(
            COUPONS, {"code": "BIG", "kind": "percent", "value": "150"}, format="json"
        )
        backwards = staff.patch(
            f"{COUPONS}{created.json()['id']}/",
            {"starts_at": "2026-05-02T00:00:00Z", "ends_at": "2026-05-01T00:00:00Z"},
            format="json",
        )
        deactivated = staff.delete(f"{COUPONS}{created.json()['id']}/").json()

        assert created.status_code == 201
        assert created.json()["code"] == "SOLDES"
        assert (detail["uses"], detail["discount_total"]) == (1, "18.00")
        assert duplicate.status_code == 409
        assert too_much.status_code == 400
        assert backwards.status_code == 400
        assert deactivated["is_active"] is False
        assert staff.get(COUPONS, {"active": "false"}).json()["meta"]["count"] == 1

    def test_only_staff_manage_coupons(self, as_user, shopper):
        assert as_user(shopper).get(COUPONS).status_code == 403
