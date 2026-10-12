from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory
from apps.catalog.domain.events import BrandChanged, ProductsChanged
from apps.catalog.models import Brand, Product
from apps.catalog.selectors import ProductDocumentSelector
from apps.catalog.tests.factories import BrandFactory, CategoryFactory, ProductFactory
from apps.media.models import UploadedMedia

pytestmark = pytest.mark.django_db

BRANDS = "/api/v1/bo/brands/"


@pytest.fixture
def staff_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(ManagerFactory.create())
    return api


@pytest.fixture
def samsung():
    return BrandFactory.create(name="Samsung", slug="samsung", position=1)


@pytest.fixture
def apple():
    return BrandFactory.create(name="Apple", slug="apple", position=2)


class TestBackoffice:
    def test_creates_with_a_unique_name_and_logo(self, staff_api):
        logo = UploadedMedia.objects.create(
            owner=ManagerFactory.create(),
            purpose="brand_logo",
            public_id="celebobo-test/brands/tecno",
            url="https://res.cloudinary.com/demo/image/upload/v1/tecno.png",
            format="png",
            bytes=1000,
        )

        created = staff_api.post(
            BRANDS, {"name": "  Tecno  Mobile ", "logo_id": logo.pk, "is_featured": True}
        )
        duplicate = staff_api.post(BRANDS, {"name": "tecno mobile"})

        assert created.status_code == 201
        assert created.json()["slug"] == "tecno-mobile"
        assert created.json()["logo"] == logo.url
        assert created.json()["is_featured"] is True
        assert duplicate.status_code == 400
        assert duplicate.json()["code"] == "brand_name_taken"

    def test_logo_must_be_a_brand_logo_upload(self, staff_api):
        photo = UploadedMedia.objects.create(
            owner=ManagerFactory.create(),
            purpose="product_image",
            public_id="celebobo-test/products/photo",
            url="https://res.cloudinary.com/demo/image/upload/v1/photo.jpg",
            format="jpg",
            bytes=1000,
        )

        response = staff_api.post(BRANDS, {"name": "Tecno", "logo_id": photo.pk})

        assert response.status_code == 400
        assert "logo_id" in response.json()["errors"]

    def test_renaming_refreshes_its_products(self, staff_api, samsung, published_events):
        product = ProductFactory.create(brand=samsung)

        response = staff_api.patch(f"{BRANDS}{samsung.pk}/", {"name": "Samsung Electronics"})

        assert response.json()["name"] == "Samsung Electronics"
        assert response.json()["slug"] == "samsung"
        assert response.json()["products_count"] == 1
        assert published_events.single(BrandChanged).brand_id == samsung.pk
        assert published_events.single(ProductsChanged).product_ids == (product.pk,)

    def test_deleting_keeps_the_products(self, staff_api, samsung):
        product = ProductFactory.create(brand=samsung)

        assert staff_api.delete(f"{BRANDS}{samsung.pk}/").status_code == 204

        product.refresh_from_db()
        assert product.brand is None

    def test_reorder(self, staff_api, samsung, apple):
        response = staff_api.post(
            f"{BRANDS}reorder/", {"ids": [apple.pk, samsung.pk]}, format="json"
        )

        assert [brand["slug"] for brand in response.json()] == ["apple", "samsung"]

    def test_resellers_cannot_manage(self, samsung):
        api = APIClient()
        api.force_authenticate(ResellerFactory.create())

        assert api.get(BRANDS).status_code == 403


class TestProductForm:
    def test_sets_and_clears_the_brand(self, staff_api, samsung):
        category = CategoryFactory.create()
        created = staff_api.post(
            "/api/v1/bo/products/",
            {
                "name": "Galaxy A55",
                "description": "Un smartphone fiable qui permet de tout faire.",
                "category_id": category.pk,
                "brand_id": samsung.pk,
                "price": "449.00",
            },
            format="json",
        ).json()
        product_id = created["id"]

        cleared = staff_api.patch(
            f"/api/v1/bo/products/{product_id}/", {"brand_id": None}, format="json"
        )
        unknown = staff_api.patch(
            f"/api/v1/bo/products/{product_id}/", {"brand_id": 999_999}, format="json"
        )

        assert created["brand"] == {"slug": "samsung", "name": "Samsung"}
        assert cleared.json()["brand"] is None
        assert unknown.status_code == 400
        assert "brand_id" in unknown.json()["errors"]


class TestStorefront:
    def test_cards_and_detail_carry_the_brand(self, api, samsung):
        ProductFactory.create(name="Galaxy A55", slug="galaxy-a55", brand=samsung)

        detail = api.get("/api/v1/products/galaxy-a55/").json()
        card = api.get("/api/v1/products/").json()["results"][0]

        assert detail["brand"] == {"slug": "samsung", "name": "Samsung"}
        assert card["brand"] == {"slug": "samsung", "name": "Samsung"}

    def test_filters_by_one_or_more_brands(self, api, samsung, apple):
        galaxy = ProductFactory.create(brand=samsung)
        iphone = ProductFactory.create(brand=apple)
        ProductFactory.create()

        def ids(params):
            return {card["id"] for card in api.get("/api/v1/products/", params).json()["results"]}

        assert ids({"brand": "samsung"}) == {galaxy.pk}
        assert ids({"brand": ["samsung", "apple"]}) == {galaxy.pk, iphone.pk}
        assert ids({"brand": "samsung,apple"}) == {galaxy.pk, iphone.pk}
        assert api.get("/api/v1/products/", {"brand": "sams ung"}).status_code == 400

    def test_lists_active_brands_with_visible_products(self, api, samsung, apple):
        ProductFactory.create(brand=samsung)
        ProductFactory.create(brand=samsung, is_active=False)
        BrandFactory.create(name="Retirée", slug="retiree", is_active=False)

        brands = api.get("/api/v1/brands/").json()

        assert [(brand["slug"], brand["products_count"]) for brand in brands] == [
            ("samsung", 1),
            ("apple", 0),
        ]

    def test_home_features_brands_that_have_products(self, api, samsung, apple):
        ProductFactory.create(brand=samsung)
        quiet = BrandFactory.create(name="Anker", slug="anker", is_featured=False)
        ProductFactory.create(brand=quiet)

        brands = api.get("/api/v1/home/").json()["brands"]

        assert [brand["slug"] for brand in brands] == ["samsung"]

    def test_search_documents_carry_the_brand(self, samsung):
        product = ProductFactory.create(brand=samsung)

        (document,) = ProductDocumentSelector().documents([product.pk])

        assert (document["brand_slug"], document["brand_name"]) == ("samsung", "Samsung")


def test_backfill_creates_brands_from_product_names():
    category = CategoryFactory.create()
    names = ("iPhone 15", "Galaxy A55", "Redmi Note 13", "Chargeur rapide 25 W", "HP 15s")
    for name in names:
        ProductFactory.create(name=name, category=category, price=Decimal(100))
    migration = import_module("apps.catalog.migrations.0006_backfill_brands")

    migration.backfill(django_apps, None)

    brands = dict(Product.objects.values_list("name", "brand__slug"))
    assert brands == {
        "iPhone 15": "apple",
        "Galaxy A55": "samsung",
        "Redmi Note 13": "xiaomi",
        "Chargeur rapide 25 W": None,
        "HP 15s": "hp",
    }
    assert Brand.objects.filter(is_featured=True).count() == 4
