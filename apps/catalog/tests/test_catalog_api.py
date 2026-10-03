from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.catalog.domain.events import ProductChanged
from apps.catalog.models import Favorite, Product
from apps.catalog.tests.factories import (
    CategoryFactory,
    FeatureFactory,
    ProductFactory,
    VariantFactory,
)
from core.container import container
from core.events.contracts import EventPublisher

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/products/"


@pytest.fixture
def phones():
    return CategoryFactory.create(name="Smartphones", slug="smartphones", icon="mobile")


@pytest.fixture
def iphone(phones) -> Product:
    product = ProductFactory.create(
        name="iPhone 15",
        slug="iphone-15",
        category=phones,
        price=Decimal(899),
        sale_price=Decimal(749),
        cost_price=Decimal(620),
        care_instructions="Nettoyer avec un chiffon doux;Éviter l'humidité",
        stock=4,
    )
    FeatureFactory.create(product=product, name="Écran OLED 6,1 pouces")
    product.options.create(name="Couleur", values=["Noir", "Bleu"])
    VariantFactory.create(
        product=product, sku="CB-1-1", label="Noir", attributes={"Couleur": "Noir"}
    )
    return product


class TestCategories:
    def test_lists_active_categories_with_visible_product_counts(self, api: APIClient, phones):
        ProductFactory.create_batch(2, category=phones)
        ProductFactory.create(category=phones, is_active=False)
        CategoryFactory.create(name="Cachée", slug="cachee", is_active=False)

        body = api.get("/api/v1/categories/").json()

        assert body == [
            {
                "id": phones.pk,
                "slug": "smartphones",
                "name": "Smartphones",
                "description": "",
                "image": "",
                "icon": "mobile",
                "products_count": 2,
            }
        ]

    def test_categories_are_cacheable(self, api: APIClient, phones):
        response = api.get("/api/v1/categories/")

        assert "public" in response["Cache-Control"]
        assert "s-maxage=60" in response["Cache-Control"]

    def test_unknown_category(self, api: APIClient):
        response = api.get("/api/v1/categories/nope/")

        assert response.status_code == 404
        assert response.json()["code"] == "category_not_found"


class TestProductList:
    def test_envelope_and_card_shape(self, api: APIClient, iphone):
        body = api.get(PRODUCTS).json()

        assert body["meta"] == {"count": 1, "page": 1, "page_size": 12, "total_pages": 1}
        card = body["results"][0]
        assert card["slug"] == "iphone-15"
        assert card["current_price"] == "749.00"
        assert card["discount_percent"] == "16.69"
        assert card["badge"] == "new"
        assert card["category"] == {
            "id": iphone.category_id,
            "slug": "smartphones",
            "name": "Smartphones",
        }
        assert card["image"].endswith("iphone-15.jpg")
        assert card["is_favorite"] is False
        assert "cost_price" not in card

    def test_filters_and_pagination_links(self, api: APIClient, phones):
        ProductFactory.create_batch(3, category=phones, price=Decimal(50))
        ProductFactory.create(category=phones, price=Decimal(500))

        body = api.get(PRODUCTS, {"max_price": "100", "page_size": "2", "ordering": "price"}).json()

        assert body["meta"]["count"] == 3
        assert body["meta"]["total_pages"] == 2
        assert "page=2" in body["next"]

    def test_repeated_ids_parameter(self, api: APIClient, phones):
        wanted = ProductFactory.create_batch(2, category=phones)
        ProductFactory.create(category=phones)

        body = api.get(f"{PRODUCTS}?ids={wanted[0].pk}&ids={wanted[1].pk}").json()

        assert {card["id"] for card in body["results"]} == {product.pk for product in wanted}

    def test_invalid_parameters_are_problems(self, api: APIClient):
        response = api.get(PRODUCTS, {"min_price": "10", "max_price": "5", "ordering": "random"})

        assert response.status_code == 400
        assert set(response.json()["errors"]) == {"ordering"}

    def test_price_range_must_be_ordered(self, api: APIClient):
        response = api.get(PRODUCTS, {"min_price": "10", "max_price": "5"})

        assert response.json()["errors"] == {
            "max_price": ["Le prix maximum doit être supérieur au prix minimum."]
        }

    def test_favorites_are_flagged_for_the_viewer(self, as_user, shopper, iphone):
        Favorite.objects.create(user=shopper, product=iphone)

        card = as_user(shopper).get(PRODUCTS).json()["results"][0]

        assert card["is_favorite"] is True

    def test_facets(self, api: APIClient, iphone):
        body = api.get(f"{PRODUCTS}facets/").json()

        assert body["categories"] == [{"value": "smartphones", "label": "Smartphones", "count": 1}]
        assert body["on_sale"] == 1


class TestProductDetail:
    def test_detail(self, api: APIClient, iphone):
        body = api.get(f"{PRODUCTS}iphone-15/").json()

        assert body["name"] == "iPhone 15"
        assert body["features"] == ["Écran OLED 6,1 pouces"]
        assert body["care_instructions"] == ["Nettoyer avec un chiffon doux", "Éviter l'humidité"]
        assert body["low_stock"] is True
        assert body["options"] == [{"name": "Couleur", "values": ["Noir", "Bleu"]}]
        assert body["variants"][0]["sku"] == "CB-1-1"
        assert body["variants"][0]["price"] == "749.00"
        assert "cost_price" not in body

    def test_hidden_products_are_not_found(self, api: APIClient, iphone):
        Product.objects.filter(pk=iphone.pk).update(is_active=False)
        container.resolve(EventPublisher).publish(ProductChanged(product_id=iphone.pk))

        response = api.get(f"{PRODUCTS}iphone-15/")

        assert response.status_code == 404
        assert response.json()["code"] == "product_not_found"

    def test_related(self, api: APIClient, iphone):
        sibling = ProductFactory.create(category=iphone.category)
        ProductFactory.create()

        body = api.get(f"{PRODUCTS}iphone-15/related/").json()

        assert [card["id"] for card in body] == [sibling.pk]


class TestCaching:
    def test_reads_are_cached_until_a_product_changes(
        self, api: APIClient, iphone, django_capture_on_commit_callbacks
    ):
        assert api.get(f"{PRODUCTS}iphone-15/").json()["name"] == "iPhone 15"
        Product.objects.filter(pk=iphone.pk).update(name="iPhone 15 Pro")

        assert api.get(f"{PRODUCTS}iphone-15/").json()["name"] == "iPhone 15"

        with django_capture_on_commit_callbacks(execute=True):
            container.resolve(EventPublisher).publish(ProductChanged(product_id=iphone.pk))

        assert api.get(f"{PRODUCTS}iphone-15/").json()["name"] == "iPhone 15 Pro"


class TestSuggest:
    def test_suggestions(self, api: APIClient, iphone, reindex):
        reindex()

        body = api.get("/api/v1/search/suggest/", {"q": "iph"}).json()

        assert body == [
            {
                "id": iphone.pk,
                "slug": "iphone-15",
                "name": "iPhone 15",
                "category": "Smartphones",
                "image": body[0]["image"],
                "current_price": "749.00",
            }
        ]

    def test_too_short(self, api: APIClient, iphone):
        assert api.get("/api/v1/search/suggest/", {"q": "i"}).json() == []
