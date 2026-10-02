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
        ("Kinshasa", "2.98", "199.00"),
        ("Autres villes", "7.50", None),
    ]


def test_quote_uses_the_delivery_city(api, phone):
    kinshasa = quote(api, phone, city=" kinshasa ")
    goma = quote(api, phone, city="Goma")
    unknown = quote(api, phone)

    assert (kinshasa["shipping_fee"], kinshasa["shipping_zone"]) == ("2.98", "Kinshasa")
    assert kinshasa["delivery_estimate"] == "24 à 48 h"
    assert (goma["shipping_fee"], goma["shipping_zone"]) == ("7.50", "Autres villes")
    assert goma["free_shipping_remaining"] is None
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
    assert order.shipping_zone == "Autres villes"
    detail = api.get(f"/api/v1/me/orders/{number}/").json()
    assert detail["shipping_zone"] == "Autres villes"


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
    assert zones["Autres villes"]["is_default"] is False
    assert updated.json()["fee"] == "8.50"
    assert staff.delete(f"{ZONES}{created.json()['id']}/").status_code == 204
    assert staff.delete(f"{ZONES}{created.json()['id']}/").status_code == 404


def test_only_staff_manage_zones(as_user):
    assert as_user(ResellerFactory.create()).get(ZONES).status_code == 403
