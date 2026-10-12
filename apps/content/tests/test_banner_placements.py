from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.content.models import Banner

pytestmark = pytest.mark.django_db

BANNERS = "/api/v1/bo/banners/"
IMAGE = "https://res.cloudinary.com/demo/image/upload/v1/banner.jpg"


def banner(staff, **fields):
    response = staff.post(BANNERS, {"title": "Visuel", "image": IMAGE, **fields}, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def test_new_fields_default_to_the_hero_carousel(as_user, manager):
    created = banner(as_user(manager))

    assert (created["placement"], created["tone"], created["eyebrow"]) == ("hero", "dark", "")
    assert created["product"] is None


@pytest.mark.parametrize(
    "placement", ["hero_mini", "deal_side", "showcase:smartphones", "column:montres-connectees"]
)
def test_accepts_known_placements(as_user, manager, placement):
    assert banner(as_user(manager), placement=placement)["placement"] == placement


@pytest.mark.parametrize("placement", ["sidebar", "showcase:", "column:Audio", "showcase:a b"])
def test_rejects_unknown_placements(as_user, manager, placement):
    response = as_user(manager).post(
        BANNERS, {"title": "Visuel", "image": IMAGE, "placement": placement}, format="json"
    )

    assert response.status_code == 400
    assert "placement" in response.json()["errors"]


def test_a_product_banner_carries_its_real_price(api, as_user, manager):
    product = ProductFactory.create(price=Decimal("139.00"), sale_price=Decimal("98.00"))
    banner(
        as_user(manager),
        placement="hero_mini",
        product_id=product.pk,
        eyebrow="Audio",
        tone="light",
    )
    api.force_authenticate(None)

    (shown,) = api.get("/api/v1/home/").json()["banners"]["hero_mini"]

    assert shown["product"]["slug"] == product.slug
    assert shown["product"]["current_price"] == "98.00"
    assert (shown["eyebrow"], shown["tone"]) == ("Audio", "light")


def test_hidden_products_are_refused(as_user, manager):
    hidden = ProductFactory.create(is_active=False)

    response = as_user(manager).post(
        BANNERS, {"title": "Visuel", "image": IMAGE, "product_id": hidden.pk}, format="json"
    )

    assert response.status_code == 400
    assert "product_id" in response.json()["errors"]


def test_home_groups_live_banners_by_placement(api):
    Banner.objects.create(title="Un", image=IMAGE, position=2)
    Banner.objects.create(title="Deux", image=IMAGE, position=1)
    Banner.objects.create(title="Côté", image=IMAGE, placement="deal_side")

    banners = api.get("/api/v1/home/").json()["banners"]

    assert {
        placement: [item["title"] for item in items] for placement, items in banners.items()
    } == {
        "hero": ["Deux", "Un"],
        "deal_side": ["Côté"],
    }


def test_list_filters_by_placement_and_reorders_within_it(as_user, manager):
    staff = as_user(manager)
    first = banner(staff, placement="hero_mini", title="A")
    second = banner(staff, placement="hero_mini", title="B")
    banner(staff, title="Carrousel")

    listed = staff.get(BANNERS, {"placement": "hero_mini"}).json()
    reordered = staff.post(
        f"{BANNERS}reorder/",
        {"placement": "hero_mini", "ids": [second["id"], first["id"]]},
        format="json",
    )
    foreign = staff.post(
        f"{BANNERS}reorder/", {"placement": "hero", "ids": [first["id"]]}, format="json"
    )

    assert [item["title"] for item in listed] == ["A", "B"]
    assert [item["title"] for item in reordered.json()] == ["B", "A"]
    assert foreign.status_code == 400
    assert "ids" in foreign.json()["errors"]
