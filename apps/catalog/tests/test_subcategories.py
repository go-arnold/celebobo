import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory
from apps.catalog.models import Category
from apps.catalog.tests.factories import CategoryFactory, ProductFactory

pytestmark = pytest.mark.django_db

CATEGORIES = "/api/v1/bo/categories/"


@pytest.fixture
def staff_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(ManagerFactory.create())
    return api


@pytest.fixture
def phones():
    return CategoryFactory.create(name="Smartphones", slug="smartphones", position=1)


@pytest.fixture
def iphone(phones):
    return CategoryFactory.create(name="iPhone", slug="iphone", parent=phones, position=2)


def test_lists_children_under_their_parent_with_counts(api, phones, iphone):
    ProductFactory.create(category=phones)
    ProductFactory.create_batch(2, category=iphone)

    (top,) = api.get("/api/v1/categories/").json()

    assert top["slug"] == "smartphones"
    assert top["products_count"] == 3
    assert [(child["slug"], child["products_count"]) for child in top["children"]] == [
        ("iphone", 2)
    ]
    assert top["children"][0]["parent"] == {
        "id": phones.pk,
        "slug": "smartphones",
        "name": "Smartphones",
    }


def test_a_sub_category_has_its_own_page(api, iphone):
    body = api.get("/api/v1/categories/iphone/").json()

    assert body["parent"]["slug"] == "smartphones"
    assert body["children"] == []


def test_the_parent_filter_includes_its_children(api, phones, iphone):
    own = ProductFactory.create(category=phones)
    nested = ProductFactory.create(category=iphone)

    def ids(slug):
        return {
            card["id"]
            for card in api.get("/api/v1/products/", {"category": slug}).json()["results"]
        }

    assert ids("smartphones") == {own.pk, nested.pk}
    assert ids("iphone") == {nested.pk}


def test_hiding_a_parent_hides_its_children(api, phones, iphone):
    ProductFactory.create(category=iphone)
    phones.is_active = False
    phones.save()

    assert api.get("/api/v1/categories/").json() == []
    assert api.get("/api/v1/products/").json()["results"] == []


def test_back_office_sets_the_parent(staff_api, phones):
    created = staff_api.post(CATEGORIES, {"name": "Android", "parent_id": phones.pk}, format="json")

    assert created.status_code == 201
    assert created.json()["parent_id"] == phones.pk


@pytest.mark.parametrize("case", ["self", "grandchild", "has_children", "unknown"])
def test_two_levels_at_most(staff_api, phones, iphone, case):
    target, parent_id = {
        "self": (phones, phones.pk),
        "grandchild": (CategoryFactory.create(name="Audio", slug="audio"), iphone.pk),
        "has_children": (phones, CategoryFactory.create(name="Tech", slug="tech").pk),
        "unknown": (phones, 999_999),
    }[case]

    response = staff_api.patch(f"{CATEGORIES}{target.pk}/", {"parent_id": parent_id}, format="json")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_category_parent"


def test_deleting_a_parent_promotes_its_children(staff_api, phones, iphone):
    assert staff_api.delete(f"{CATEGORIES}{phones.pk}/").status_code == 204

    assert Category.objects.get(pk=iphone.pk).parent is None
