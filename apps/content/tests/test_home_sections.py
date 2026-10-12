import pytest

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.content.models import HomeSection

pytestmark = pytest.mark.django_db

SECTIONS = "/api/v1/bo/home-sections/"


@pytest.fixture
def phones(db):
    return CategoryFactory.create(name="Smartphones", slug="smartphones")


def test_home_returns_sections_with_products_and_sub_categories(api, phones):
    iphone = CategoryFactory.create(name="iPhone", slug="iphone", parent=phones)
    product = ProductFactory.create(category=iphone)
    audio = CategoryFactory.create(name="Audio", slug="audio")
    HomeSection.objects.create(
        kind="showcase", category=phones, title="Top smartphones", position=1
    )
    HomeSection.objects.create(kind="column", category=audio, position=2)
    HomeSection.objects.create(kind="column", category=audio, position=3, is_active=False)

    sections = api.get("/api/v1/home/").json()["sections"]

    assert [(item["kind"], item["title"]) for item in sections] == [
        ("showcase", "Top smartphones"),
        ("column", "Audio"),
    ]
    assert [card["id"] for card in sections[0]["products"]] == [product.pk]
    assert [child["slug"] for child in sections[0]["category"]["children"]] == ["iphone"]


def test_hidden_categories_are_skipped(api, phones):
    phones.is_active = False
    phones.save()
    HomeSection.objects.create(kind="showcase", category=phones)

    assert api.get("/api/v1/home/").json()["sections"] == []


def test_back_office_creates_appends_and_reorders(as_user, manager, phones):
    audio = CategoryFactory.create(name="Audio", slug="audio")
    staff = as_user(manager)

    first = staff.post(SECTIONS, {"kind": "showcase", "category_id": phones.pk}, format="json")
    second = staff.post(SECTIONS, {"kind": "column", "category_id": audio.pk}, format="json")
    reordered = staff.post(
        f"{SECTIONS}reorder/", {"ids": [second.json()["id"], first.json()["id"]]}, format="json"
    )

    assert (first.json()["position"], second.json()["position"]) == (1, 2)
    assert [item["kind"] for item in reordered.json()] == ["column", "showcase"]


def test_rejects_hidden_categories(as_user, manager, phones):
    hidden = CategoryFactory.create(name="Cachée", slug="cachee", is_active=False)

    response = as_user(manager).post(
        SECTIONS, {"kind": "showcase", "category_id": hidden.pk}, format="json"
    )

    assert response.status_code == 400
    assert response.json()["code"] == "section_category_unavailable"


def test_resellers_cannot_manage(as_user, reseller):
    assert as_user(reseller).get(SECTIONS).status_code == 403
