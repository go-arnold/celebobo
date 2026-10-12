from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.domain.events import ProductsChanged
from apps.catalog.facades import DealAdminFacade
from apps.catalog.models import Deal
from apps.catalog.tests.factories import ProductFactory, VariantFactory
from apps.orders.models import OrderItem
from core.container import container

DEALS = "/api/v1/bo/deals/"
QUOTE = "/api/v1/checkout/quote/"

pytestmark = pytest.mark.django_db


def window(*, starts_in: int = -1, hours: int = 24) -> dict[str, str]:
    start = timezone.now() + timedelta(hours=starts_in)
    return {
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=hours)).isoformat(),
    }


@pytest.fixture
def create_deal(as_user, manager):
    def create(product, **fields):
        payload = {"product_id": product.pk, "deal_price": "99.00", **window(), **fields}
        response = as_user(manager).post(DEALS, payload, format="json")
        assert response.status_code == 201, response.json()
        return response.json()

    return create


def quoted_price(api, product, quantity=1, variant=None):
    line = {"product_id": product.pk, "quantity": quantity}
    if variant is not None:
        line["variant_id"] = variant.pk
    return api.post(QUOTE, {"lines": [line]}, format="json").json()["lines"][0]["unit_price"]


class TestBackoffice:
    def test_creates_and_lists_by_status(self, as_user, manager, phone, create_deal):
        live = create_deal(phone, quantity=3, gift_label="  Coque offerte ")
        later = create_deal(ProductFactory.create(price=Decimal(200)), **window(starts_in=5))

        assert live["status"] == "live"
        assert live["regular_price"] == "120.00"
        assert live["sold"] == 0
        assert live["gift_label"] == "Coque offerte"
        assert live["product"]["slug"] == "galaxy-a55"
        assert later["status"] == "scheduled"
        listed = as_user(manager).get(DEALS, {"status": "scheduled"}).json()
        assert [deal["id"] for deal in listed] == [later["id"]]

    @pytest.mark.parametrize(
        ("fields", "field"),
        [
            ({"deal_price": "120.00"}, "deal_price"),
            ({"starts_at": "2026-10-12T10:00:00Z", "ends_at": "2026-10-12T09:00:00Z"}, "ends_at"),
        ],
    )
    def test_rejects_invalid_terms(self, as_user, manager, phone, fields, field):
        payload = {"product_id": phone.pk, "deal_price": "99.00", **window(), **fields}

        response = as_user(manager).post(DEALS, payload, format="json")

        assert response.status_code == 400
        assert field in response.json()["errors"]

    def test_rejects_overlapping_deals(self, as_user, manager, phone, create_deal):
        create_deal(phone)

        response = as_user(manager).post(
            DEALS,
            {"product_id": phone.pk, "deal_price": "90.00", **window(starts_in=2)},
            format="json",
        )

        assert response.status_code == 400
        assert "starts_at" in response.json()["errors"]

    def test_products_with_variants_need_one(self, as_user, manager):
        product = ProductFactory.create(price=Decimal(300))
        VariantFactory.create(product=product)

        response = as_user(manager).post(
            DEALS, {"product_id": product.pk, "deal_price": "250.00", **window()}, format="json"
        )

        assert response.status_code == 400
        assert "variant_id" in response.json()["errors"]

    def test_update_and_delete(self, as_user, manager, phone, create_deal):
        deal = create_deal(phone)

        patched = as_user(manager).patch(
            f"{DEALS}{deal['id']}/", {"deal_price": "89.00", "is_active": False}, format="json"
        )
        deleted = as_user(manager).delete(f"{DEALS}{deal['id']}/")

        assert patched.json()["deal_price"] == "89.00"
        assert patched.json()["status"] == "ended"
        assert deleted.status_code == 204
        assert not Deal.objects.exists()

    def test_requires_product_management(self, as_user, shopper):
        assert as_user(shopper).get(DEALS).status_code == 403


class TestStorefront:
    def test_live_deal_reprices_card_detail_and_home(self, api, phone, create_deal):
        create_deal(phone, quantity=20, gift_label="Coque offerte")

        detail = api.get("/api/v1/products/galaxy-a55/").json()
        home = api.get("/api/v1/home/").json()

        assert detail["current_price"] == "99.00"
        assert detail["price"] == "120.00"
        assert detail["discount_percent"] == "17.50"
        assert home["deal"]["product"]["slug"] == "galaxy-a55"
        assert home["deal"]["deal_price"] == "99.00"
        assert home["deal"]["regular_price"] == "120.00"
        assert home["deal"]["quantity"] == 20
        assert home["deal"]["sold"] == 0
        assert home["deal"]["gift_label"] == "Coque offerte"

    def test_unlimited_deal_has_no_counter(self, api, phone, create_deal):
        create_deal(phone)

        deal = api.get("/api/v1/home/").json()["deal"]

        assert deal["quantity"] is None
        assert deal["sold"] is None

    def test_no_live_deal_means_null(self, api, phone, create_deal):
        create_deal(phone, **window(starts_in=3))

        assert api.get("/api/v1/home/").json()["deal"] is None
        assert quoted_price(api, phone) == "120.00"

    def test_variant_deal_only_reprices_that_variant(self, api, create_deal):
        product = ProductFactory.create(price=Decimal(300), stock=0)
        small = VariantFactory.create(product=product, price=None, stock=4)
        large = VariantFactory.create(product=product, price=Decimal(350), stock=4)
        create_deal(product, variant_id=large.pk, deal_price="299.00")

        variants = {
            variant["id"]: variant["price"]
            for variant in api.get(f"/api/v1/products/{product.slug}/").json()["variants"]
        }

        assert variants == {small.pk: "300.00", large.pk: "299.00"}
        assert quoted_price(api, product, variant=large) == "299.00"
        assert quoted_price(api, product, variant=small) == "300.00"


class TestOrders:
    def test_orders_pay_the_deal_price_until_sold_out(
        self, api, shopper, phone, create_deal, place_order
    ):
        deal = create_deal(phone, quantity=2)

        first = place_order(shopper, phone, quantity=2)

        assert first["items"][0]["unit_price"] == "99.00"
        assert OrderItem.objects.get().deal_id == deal["id"]
        assert quoted_price(api, phone) == "120.00"
        assert api.get("/api/v1/home/").json()["deal"] is None

    def test_a_line_larger_than_what_is_left_pays_the_regular_price(self, api, phone, create_deal):
        create_deal(phone, quantity=2)

        assert quoted_price(api, phone, quantity=3) == "120.00"
        assert quoted_price(api, phone, quantity=2) == "99.00"

    def test_cancelling_gives_the_units_back(
        self, as_user, shopper, phone, create_deal, place_order
    ):
        create_deal(phone, quantity=1)
        number = place_order(shopper, phone)["number"]
        api = as_user(shopper)

        api.post(f"/api/v1/me/orders/{number}/cancel/", {"reason": "changed_mind"})

        assert api.get("/api/v1/home/").json()["deal"]["sold"] == 0
        assert quoted_price(api, phone) == "99.00"


class TestClock:
    def test_announces_each_transition_once(self, phone, published_events):
        deal = Deal.objects.create(
            product=phone,
            deal_price=Decimal(99),
            starts_at=timezone.now() - timedelta(minutes=1),
            ends_at=timezone.now() + timedelta(hours=1),
            announced="scheduled",
        )
        clock = container.resolve(DealAdminFacade)

        assert clock.announce() == [phone.pk]
        assert clock.announce() == []
        Deal.objects.filter(pk=deal.pk).update(ends_at=timezone.now())
        assert clock.announce() == [phone.pk]
        assert [event.product_ids for event in published_events.of_type(ProductsChanged)] == [
            (phone.pk,),
            (phone.pk,),
        ]
