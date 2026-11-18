from decimal import Decimal

import pytest

from apps.accounts.tests.factories import ResellerFactory
from apps.orders.models import Order, ShippingZone
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db

QUOTE = "/api/v1/checkout/quote/"
ZONES = "/api/v1/bo/shipping-zones/"


def quote(api, product, **extra):
    return api.post(
        QUOTE, {"lines": [{"product_id": product.pk, "quantity": 1}], **extra}, format="json"
    ).json()


def test_seeded_zones_are_public(api):
    zones = api.get("/api/v1/shipping/zones/").json()

    assert [(zone["name"], zone["fee"], zone["free_threshold"]) for zone in zones] == [
        ("Bukavu", "2.98", "199.00"),
        ("Goma", "2.98", "199.00"),
        ("Environs de Bukavu et Goma", "5.00", None),
        ("Reste du pays", "7.50", None),
    ]
    assert zones[-1]["is_default"] is True


def test_quote_uses_the_delivery_city(api, phone):
    goma = quote(api, phone, city=" goma ")
    uvira = quote(api, phone, city="Uvira")
    kinshasa = quote(api, phone, city="Kinshasa")
    unknown = quote(api, phone)

    assert (goma["shipping_fee"], goma["shipping_zone"]) == ("2.98", "Goma")
    assert goma["delivery_estimate"] == "24 à 48 h"
    assert (uvira["shipping_fee"], uvira["shipping_zone"]) == ("5.00", "Environs de Bukavu et Goma")
    assert (kinshasa["shipping_fee"], kinshasa["shipping_zone"]) == ("7.50", "Reste du pays")
    assert kinshasa["free_shipping_remaining"] is None
    assert unknown["shipping_fee"] == "2.98"


def test_without_zones_the_settings_apply(api, phone):
    ShippingZone.objects.all().delete()

    assert quote(api, phone, city="Goma")["shipping_fee"] == "2.98"


def test_cart_and_checkout_use_the_address_city(as_user, shopper, phone, place_order):
    api = as_user(shopper)
    api.post("/api/v1/cart/items/", {"product_id": phone.pk, "quantity": 1}, format="json")

    cart = api.get("/api/v1/cart/", {"city": "Lubumbashi"}).json()
    number = place_order(shopper, phone, address={**ADDRESS, "city": "Lubumbashi"})["number"]

    order = Order.objects.get(number=number)
    assert cart["quote"]["shipping_fee"] == "7.50"
    assert order.shipping_fee == Decimal("7.50")
    assert order.shipping_zone == "Reste du pays"
    detail = api.get(f"/api/v1/me/orders/{number}/").json()
    assert detail["shipping_zone"] == "Reste du pays"


def test_zone_management(as_user, manager):
    staff = as_user(manager)

    created = staff.post(
        ZONES,
        {"name": "Est", "fee": "9.00", "cities": ["Goma", " Bukavu ", "Goma"], "is_default": True},
        format="json",
    )
    zones = {zone["name"]: zone for zone in staff.get(ZONES).json()}
    updated = staff.patch(f"{ZONES}{created.json()['id']}/", {"fee": "8.50"}, format="json")

    assert created.status_code == 201
    assert zones["Est"]["cities"] == ["Goma", "Bukavu"]
    assert zones["Est"]["is_default"] is True
    assert zones["Reste du pays"]["is_default"] is False
    assert updated.json()["fee"] == "8.50"
    assert staff.delete(f"{ZONES}{created.json()['id']}/").status_code == 204
    assert staff.delete(f"{ZONES}{created.json()['id']}/").status_code == 404


def test_zones_are_reordered_in_one_call(as_user, manager):
    staff = as_user(manager)
    ids = [zone["id"] for zone in staff.get(ZONES).json()]

    response = staff.post(f"{ZONES}reorder/", {"ids": ids[::-1]}, format="json")
    unknown = staff.post(f"{ZONES}reorder/", {"ids": [*ids, 999]}, format="json")

    assert [zone["id"] for zone in response.json()] == ids[::-1]
    assert [zone["position"] for zone in response.json()] == list(range(1, len(ids) + 1))
    assert unknown.status_code == 404


def test_only_staff_manage_zones(as_user):
    assert as_user(ResellerFactory.create()).get(ZONES).status_code == 403


@pytest.fixture
def policy_zones(db):
    # the delivery policy's last rows: other places quoted on request, pickup at the shop
    ShippingZone.objects.filter(is_default=True).update(pricing="quote")
    return ShippingZone.objects.create(
        name="Retrait sur place",
        fee=Decimal(0),
        pricing="pickup",
        pickup_address="Avenue Mwanga n° 21, Nyalukemba, Bukavu",
        delivery_estimate="Dès confirmation",
    )


def test_quote_flags_a_zone_quoted_on_request(api, phone, policy_zones):
    far = quote(api, phone, city="Kisangani")
    near = quote(api, phone, city="Bukavu")

    assert (far["shipping_fee"], far["shipping_quote_required"]) == ("0.00", True)
    assert far["free_shipping_remaining"] is None
    assert (near["shipping_fee"], near["shipping_quote_required"]) == ("2.98", False)
    assert near["pickup_available"] is True


def test_pickup_is_free_and_never_matched_from_a_city(api, phone, policy_zones):
    pickup = quote(api, phone, city="Kisangani", pickup=True)
    by_name = quote(api, phone, city="Retrait sur place")

    assert pickup["shipping_fee"] == "0.00"
    assert pickup["delivery_method"] == "pickup"
    assert pickup["pickup_address"] == "Avenue Mwanga n° 21, Nyalukemba, Bukavu"
    assert pickup["shipping_quote_required"] is False
    assert by_name["shipping_zone"] == "Reste du pays"


def test_checkout_records_a_pickup_order(as_user, shopper, phone, place_order, policy_zones):
    number = place_order(shopper, phone, pickup=True)["number"]

    order = Order.objects.get(number=number)
    assert (order.delivery_method, order.shipping_fee) == ("pickup", Decimal(0))
    assert order.shipping_zone == "Retrait sur place"
    assert order.pickup_address == "Avenue Mwanga n° 21, Nyalukemba, Bukavu"
    assert order.awaiting_shipping_quote is False
    # the address still gives the client's contact details
    assert (order.recipient, order.phone) == ("Aline Mbuyi", "+243 81 234 5678")
    detail = as_user(shopper).get(f"/api/v1/me/orders/{number}/").json()
    assert detail["delivery_method"] == "pickup"
    assert detail["pickup_address"] == order.pickup_address
    assert detail["delivery_estimate"] == "Dès confirmation"


def test_checkout_in_a_quoted_zone_waits_for_the_fee(shopper, phone, place_order, policy_zones):
    number = place_order(shopper, phone, address={**ADDRESS, "city": "Kisangani"})["number"]

    order = Order.objects.get(number=number)
    assert (order.shipping_fee, order.total) == (Decimal(0), order.subtotal)
    assert order.awaiting_shipping_quote is True


def test_pickup_needs_a_pickup_zone(api, phone):
    response = api.post(
        QUOTE,
        {"lines": [{"product_id": phone.pk, "quantity": 1}], "pickup": True},
        format="json",
    )

    assert response.json()["code"] == "pickup_unavailable"


def test_a_pickup_zone_needs_an_address_and_stays_unique(as_user, manager, policy_zones):
    staff = as_user(manager)

    second = staff.post(
        ZONES, {"name": "Boutique Goma", "fee": "0", "pricing": "pickup"}, format="json"
    )
    moved = staff.patch(f"{ZONES}{policy_zones.pk}/", {"pickup_address": " "}, format="json")

    assert set(second.json()["errors"]) == {"pickup_address", "pricing"}
    assert set(moved.json()["errors"]) == {"pickup_address"}
    listed = {zone["name"]: zone for zone in staff.get(ZONES).json()}
    assert listed["Retrait sur place"]["pricing"] == "pickup"
    assert listed["Reste du pays"]["pricing"] == "quote"
