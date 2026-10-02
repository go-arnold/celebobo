from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.domain.events import ProductChanged, ProductRemoved, StockLow
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.facades import InventoryFacade
from apps.catalog.models import Category, Product, ProductVariant, StockMovement
from apps.catalog.tests.factories import CategoryFactory, ProductFactory, ReviewFactory
from apps.media.models import UploadedMedia
from core.container import container

pytestmark = pytest.mark.django_db

PRODUCTS = "/api/v1/bo/products/"


@pytest.fixture
def manager():
    return ManagerFactory.create()


@pytest.fixture
def staff_api(manager) -> APIClient:
    api = APIClient()
    api.force_authenticate(manager)
    return api


@pytest.fixture
def phones():
    return CategoryFactory.create(name="Smartphones", slug="smartphones")


def upload(owner, purpose="product_image", name="photo"):
    return UploadedMedia.objects.create(
        owner=owner,
        purpose=purpose,
        public_id=f"celebobo-test/{purpose}/{name}",
        url=f"https://res.cloudinary.com/demo/image/upload/v1/{name}.jpg",
        format="jpg",
        bytes=1000,
    )


def payload(category, **overrides):
    return {
        "name": "Galaxy A55",
        "description": "Un smartphone fiable qui permet de tout faire.",
        "category_id": category.pk,
        "price": "320.00",
        "cost_price": "240.00",
        "features": ["Écran 6,6 pouces", "  Écran 6,6 pouces ", "5G"],
        "stock": 4,
        **overrides,
    }


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


class TestProductCreation:
    def test_creates_with_slug_images_stock_and_margin(
        self, staff_api, manager, phones, published_events
    ):
        first, second = upload(manager, name="front"), upload(manager, name="back")

        response = staff_api.post(PRODUCTS, payload(phones, image_ids=[second.pk, first.pk]))

        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "galaxy-a55"
        assert body["features"] == ["Écran 6,6 pouces", "5G"]
        assert [image["url"] for image in body["images"]] == [second.url, first.url]
        assert body["stock"] == 4
        assert body["margin"] == "80.00"
        assert body["margin_percent"] == "25.00"
        movement = StockMovement.objects.get()
        assert (movement.delta, movement.reason, movement.note) == (4, "inventory", "Stock initial")
        assert published_events.single(ProductChanged).product_id == body["id"]

    def test_slugs_stay_unique(self, staff_api, phones):
        staff_api.post(PRODUCTS, payload(phones))

        assert staff_api.post(PRODUCTS, payload(phones)).json()["slug"] == "galaxy-a55-2"

    def test_new_products_are_searchable_immediately(
        self, staff_api, phones, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            staff_api.post(PRODUCTS, payload(phones, name="Écouteurs Pulse"))

        results = APIClient().get("/api/v1/products/", {"search": "ecouteurs"}).json()["results"]
        assert [card["name"] for card in results] == ["Écouteurs Pulse"]

    @pytest.mark.parametrize(
        ("overrides", "code", "field"),
        [
            ({"sale_price": "320.00"}, "invalid_pricing", "sale_price"),
            ({"image_ids": [999]}, "unknown_images", "image_ids"),
            ({"category_id": 999}, "validation_failed", "category_id"),
            (
                {"sell_by": (timezone.localdate() - timedelta(days=1)).isoformat()},
                "sell_by_in_past",
                "sell_by",
            ),
            (
                {
                    "options": [
                        {"name": "Couleur", "values": ["Noir"]},
                        {"name": "couleur", "values": ["Bleu"]},
                    ]
                },
                "invalid_variant_attributes",
                "attributes",
            ),
        ],
    )
    def test_validation(self, staff_api, phones, overrides, code, field):
        response = staff_api.post(PRODUCTS, payload(phones, **overrides))

        assert response.status_code == 400
        assert response.json()["code"] == code
        assert field in response.json()["errors"]

    def test_customer_images_cannot_be_used(self, staff_api, phones):
        avatar = upload(UserFactory.create(), purpose="avatar")

        response = staff_api.post(PRODUCTS, payload(phones, image_ids=[avatar.pk]))

        assert response.json()["code"] == "unknown_images"


class TestProductManagement:
    def test_partial_update(self, staff_api, phones):
        product = ProductFactory.create(category=phones, badge="best_seller")

        body = staff_api.patch(
            f"{PRODUCTS}{product.pk}/",
            {"price": "150.00", "sale_price": "120.00", "badge": None, "features": ["Neuf"]},
        ).json()

        assert body["current_price"] == "120.00"
        assert body["badge"] is None
        assert body["features"] == ["Neuf"]

    def test_update_keeps_pricing_consistent(self, staff_api, phones):
        product = ProductFactory.create(category=phones, price=Decimal(100), sale_price=Decimal(80))

        response = staff_api.patch(f"{PRODUCTS}{product.pk}/", {"price": "70.00"})

        assert response.json()["code"] == "invalid_pricing"

    def test_trash_restore_duplicate(self, staff_api, phones, published_events):
        product = ProductFactory.create(category=phones, name="Pixel 9", slug="pixel-9")

        assert staff_api.delete(f"{PRODUCTS}{product.pk}/").status_code == 204
        trashed = staff_api.get(PRODUCTS, {"status": "trash"}).json()
        restored = staff_api.post(f"{PRODUCTS}{product.pk}/restore/").json()
        copy = staff_api.post(f"{PRODUCTS}{product.pk}/duplicate/").json()

        assert [row["id"] for row in trashed["results"]] == [product.pk]
        assert restored["status"] == "active"
        assert copy["name"] == "Pixel 9 (copie)"
        assert copy["status"] == "inactive"
        assert copy["stock"] == 0
        assert published_events.single(ProductRemoved).product_id == product.pk

    def test_list_filters_and_stats(self, staff_api, phones):
        ProductFactory.create(category=phones, stock=2, stock_threshold=5, cost_price=Decimal(10))
        ProductFactory.create(category=phones, stock=0)
        ProductFactory.create(category=phones, stock=20, cost_price=Decimal(5), is_active=False)

        low = staff_api.get(PRODUCTS, {"low_stock": "true"}).json()
        everything = staff_api.get(PRODUCTS, {"status": "all"}).json()

        assert low["meta"]["count"] == 1
        assert everything["meta"]["count"] == 3
        assert everything["meta"]["stats"] == {
            "total": 3,
            "active": 2,
            "on_sale": 0,
            "out_of_stock": 1,
            "low_stock": 1,
            "stock_value": "120.00",
            "trashed": 0,
        }

    def test_bulk_actions(self, staff_api, phones):
        products = ProductFactory.create_batch(2, category=phones, price=Decimal(100))
        audio = CategoryFactory.create(name="Audio", slug="audio")
        ids = [product.pk for product in products]

        discount = staff_api.post(
            f"{PRODUCTS}bulk/", {"ids": ids, "action": "set_discount", "percent": "20"}
        )
        move = staff_api.post(
            f"{PRODUCTS}bulk/", {"ids": ids, "action": "set_category", "category_id": audio.pk}
        )
        trash = staff_api.post(f"{PRODUCTS}bulk/", {"ids": ids, "action": "trash"})

        assert sorted(discount.json()["updated"]) == sorted(ids)
        assert set(Product.all_objects.values_list("sale_price", flat=True)) == {Decimal("80.00")}
        assert sorted(move.json()["updated"]) == sorted(ids)
        assert trash.json()["updated"]
        assert Product.objects.count() == 0

    def test_invalid_discount(self, staff_api, phones):
        product = ProductFactory.create(category=phones)

        response = staff_api.post(
            f"{PRODUCTS}bulk/", {"ids": [product.pk], "action": "set_discount", "percent": "95"}
        )

        assert response.status_code == 400

    @pytest.mark.parametrize(
        ("factory", "list_status", "create_status"),
        [(ResellerFactory, 200, 403), (UserFactory, 403, 403)],
    )
    def test_permissions(self, phones, factory, list_status, create_status):
        api = as_api(factory.create())

        assert api.get(PRODUCTS).status_code == list_status
        assert api.post(PRODUCTS, payload(phones)).status_code == create_status


class TestVariants:
    @pytest.fixture
    def phone(self, staff_api, phones):
        body = staff_api.post(
            PRODUCTS,
            payload(
                phones,
                stock=0,
                options=[
                    {"name": "Couleur", "values": ["Noir", "Bleu"]},
                    {"name": "Stockage", "values": ["128 Go", "256 Go"]},
                ],
            ),
        ).json()
        return Product.objects.get(pk=body["id"])

    def variants_url(self, product):
        return f"{PRODUCTS}{product.pk}/variants/"

    def test_add_variants_and_track_total_stock(self, staff_api, phone):
        first = staff_api.post(
            self.variants_url(phone),
            {"attributes": {"Stockage": "128 Go", "Couleur": "Noir"}, "stock": 3},
        )
        second = staff_api.post(
            self.variants_url(phone),
            {
                "attributes": {"Couleur": "Bleu", "Stockage": "256 Go"},
                "stock": 2,
                "price": "380.00",
            },
        )

        assert first.status_code == 201
        variants = second.json()["variants"]
        assert [variant["label"] for variant in variants] == ["Noir / 128 Go", "Bleu / 256 Go"]
        assert variants[0]["sku"] == f"CB-{phone.pk}-1"
        assert second.json()["stock"] == 5

    @pytest.mark.parametrize(
        "attributes",
        [
            {"Couleur": "Rouge", "Stockage": "128 Go"},
            {"Couleur": "Noir"},
            {"Couleur": "Noir", "Stockage": "128 Go", "Taille": "M"},
        ],
    )
    def test_attributes_must_match_options(self, staff_api, phone, attributes):
        response = staff_api.post(self.variants_url(phone), {"attributes": attributes})

        assert response.json()["code"] == "invalid_variant_attributes"

    def test_duplicates_are_rejected(self, staff_api, phone):
        attributes = {"Couleur": "Noir", "Stockage": "128 Go"}
        staff_api.post(self.variants_url(phone), {"attributes": attributes, "sku": "cb-x"})

        same = staff_api.post(self.variants_url(phone), {"attributes": attributes})
        sku = staff_api.post(
            self.variants_url(phone),
            {"attributes": {"Couleur": "Bleu", "Stockage": "128 Go"}, "sku": "CB-X"},
        )

        assert same.json()["code"] == "duplicate_variant"
        assert sku.json()["code"] == "duplicate_sku"

    def test_update_and_remove(self, staff_api, phone):
        staff_api.post(
            self.variants_url(phone),
            {"attributes": {"Couleur": "Noir", "Stockage": "128 Go"}, "stock": 3},
        )
        variant = ProductVariant.objects.get()

        patched = staff_api.patch(
            f"/api/v1/bo/variants/{variant.pk}/", {"price": "299.00", "is_active": False}
        )
        removed = staff_api.delete(f"/api/v1/bo/variants/{variant.pk}/")

        assert patched.json()["variants"][0]["price"] == "299.00"
        assert patched.json()["stock"] == 0
        variant.refresh_from_db()
        assert removed.status_code == 200
        assert variant.is_active is False


class TestStock:
    def url(self, product, suffix="stock-adjustments"):
        return f"{PRODUCTS}{product.pk}/{suffix}/"

    def test_delta_and_set_adjustments(self, staff_api, phones, manager):
        product = ProductFactory.create(category=phones, stock=10)

        restock = staff_api.post(
            self.url(product), {"value": 5, "reason": "restock", "note": "Arrivage"}
        )
        count = staff_api.post(
            self.url(product), {"mode": "set", "value": 12, "reason": "inventory"}
        )
        history = staff_api.get(self.url(product, "stock-movements")).json()

        assert restock.status_code == 201
        assert restock.json()["balance_after"] == 15
        assert count.json()["delta"] == -3
        assert count.json()["actor_name"] == f"{manager.first_name} {manager.last_name}"
        assert [item["reason"] for item in history["results"]] == ["inventory", "restock"]

    def test_stock_cannot_go_negative(self, staff_api, phones):
        product = ProductFactory.create(category=phones, stock=1)

        response = staff_api.post(self.url(product), {"value": -2, "reason": "loss"})

        assert response.json()["code"] == "negative_stock"

    def test_products_with_variants_need_a_variant(self, staff_api, phones):
        product = ProductFactory.create(category=phones)
        product.variants.create(sku="CB-V-1", label="Noir", attributes={"Couleur": "Noir"}, stock=1)

        response = staff_api.post(self.url(product), {"value": 1, "reason": "restock"})

        assert response.json()["code"] == "variants_manage_stock"

    def test_low_stock_is_announced_and_listed(self, staff_api, phones, published_events):
        product = ProductFactory.create(category=phones, stock=8, stock_threshold=5)

        staff_api.post(self.url(product), {"value": -4, "reason": "loss"})
        alerts = staff_api.get("/api/v1/bo/stock/alerts/").json()

        low = published_events.single(StockLow)
        assert (low.product_id, low.stock, low.threshold) == (product.pk, 4, 5)
        assert alerts == [
            {
                "product_id": product.pk,
                "variant_id": None,
                "name": product.name,
                "variant_label": "",
                "stock": 4,
                "threshold": 5,
            }
        ]

    def test_checkout_reservations_announce_low_stock(self, phones, published_events):
        product = ProductFactory.create(category=phones, stock=6, stock_threshold=5)

        container.resolve(InventoryFacade).reserve(
            [StockLine(product_id=product.pk, quantity=2)], StockSource(kind="order", id=1)
        )

        assert published_events.single(StockLow).stock == 4


class TestCategories:
    url = "/api/v1/bo/categories/"

    def test_create_update_reorder(self, staff_api, manager):
        image = upload(manager, purpose="category_image")

        audio = staff_api.post(
            self.url, {"name": " Audio ", "icon": "headphone", "image_id": image.pk}
        ).json()
        gaming = staff_api.post(self.url, {"name": "Gaming"}).json()
        duplicate = staff_api.post(self.url, {"name": "audio"})
        renamed = staff_api.patch(
            f"{self.url}{audio['id']}/", {"name": "Son & audio", "is_active": False}
        ).json()
        ordered = staff_api.post(f"{self.url}reorder/", {"ids": [gaming["id"], audio["id"]]}).json()

        assert audio["slug"] == "audio"
        assert audio["image"] == image.url
        assert duplicate.json()["code"] == "category_name_taken"
        assert renamed["name"] == "Son & audio"
        assert renamed["is_active"] is False
        assert [item["id"] for item in ordered] == [gaming["id"], audio["id"]]

    def test_non_empty_categories_need_a_destination(self, staff_api, phones):
        ProductFactory.create_batch(2, category=phones)
        target = CategoryFactory.create(name="Divers", slug="divers")

        blocked = staff_api.delete(f"{self.url}{phones.pk}/")
        moved = staff_api.delete(f"{self.url}{phones.pk}/?move_to={target.pk}")

        assert blocked.status_code == 409
        assert blocked.json()["meta"] == {"products_count": 2}
        assert moved.status_code == 204
        assert Product.objects.filter(category=target).count() == 2
        assert not Category.objects.filter(pk=phones.pk).exists()

    def test_resellers_cannot_manage_categories(self):
        assert as_api(ResellerFactory.create()).get(self.url).status_code == 403


class TestReviewModeration:
    def test_hiding_a_review_updates_the_rating(self, staff_api, phones):
        product = ProductFactory.create(category=phones)
        keep = ReviewFactory.create(product=product, user=UserFactory.create(), rating=5)
        hide = ReviewFactory.create(product=product, user=UserFactory.create(), rating=1)
        Product.objects.filter(pk=product.pk).update(rating_avg=Decimal(3), reviews_count=2)

        listed = staff_api.get("/api/v1/bo/reviews/", {"rating": 1}).json()
        moderated = staff_api.patch(f"/api/v1/bo/reviews/{hide.pk}/", {"status": "hidden"})

        assert [item["id"] for item in listed["results"]] == [hide.pk]
        assert moderated.json()["status"] == "hidden"
        product.refresh_from_db()
        assert (product.rating_avg, product.reviews_count) == (Decimal("5.00"), 1)
        assert keep.status == "published"


class TestManagementEdges:
    def test_update_replaces_options_images_and_category(self, staff_api, manager, phones):
        product = ProductFactory.create(category=phones)
        audio = CategoryFactory.create(name="Audio", slug="audio")
        image = upload(manager, name="side")

        body = staff_api.patch(
            f"{PRODUCTS}{product.pk}/",
            {
                "category_id": audio.pk,
                "options": [{"name": " Couleur ", "values": ["Noir", "Noir", " Bleu "]}],
                "image_ids": [image.pk],
                "name": "  Pixel   9 Pro ",
                "badge": "best_seller",
            },
        ).json()

        assert body["category"]["slug"] == "audio"
        assert body["options"] == [{"name": "Couleur", "values": ["Noir", "Bleu"]}]
        assert [item["url"] for item in body["images"]] == [image.url]
        assert body["name"] == "Pixel 9 Pro"
        assert body["badge"] == "best_seller"

    def test_bulk_restore_activate_and_clear_discount(self, staff_api, phones):
        product = ProductFactory.create(
            category=phones, price=Decimal(100), sale_price=Decimal(90), is_active=False
        )
        product.delete()
        url = f"{PRODUCTS}bulk/"

        restored = staff_api.post(url, {"ids": [product.pk], "action": "restore"}).json()
        activated = staff_api.post(url, {"ids": [product.pk], "action": "activate"}).json()
        cleared = staff_api.post(url, {"ids": [product.pk], "action": "clear_discount"}).json()
        noop = staff_api.post(url, {"ids": [product.pk], "action": "restore"}).json()

        product.refresh_from_db()
        assert restored["updated"] == activated["updated"] == cleared["updated"] == [product.pk]
        assert noop["updated"] == []
        assert product.is_active is True
        assert product.sale_price is None

    def test_variant_edits_are_validated(self, staff_api, phones):
        product = ProductFactory.create(category=phones)
        product.options.create(name="Couleur", values=["Noir", "Bleu"])
        first = product.variants.create(sku="CB-A", label="Noir", attributes={"Couleur": "Noir"})
        product.variants.create(sku="CB-B", label="Bleu", attributes={"Couleur": "Bleu"})
        url = f"/api/v1/bo/variants/{first.pk}/"

        clash = staff_api.patch(url, {"attributes": {"Couleur": "Bleu"}})
        sku = staff_api.patch(url, {"sku": "cb-b"})
        price = staff_api.patch(url, {"price": "0.00"})
        renamed = staff_api.patch(url, {"sku": "cb-noir", "attributes": {"Couleur": "Noir"}})

        assert clash.json()["code"] == "duplicate_variant"
        assert sku.json()["code"] == "duplicate_sku"
        assert price.json()["code"] == "invalid_pricing"
        assert renamed.json()["variants"][0]["sku"] == "CB-NOIR"

    def test_unused_variants_are_deleted(self, staff_api, phones):
        product = ProductFactory.create(category=phones)
        product.options.create(name="Couleur", values=["Noir"])
        variant = product.variants.create(sku="CB-Z", label="Noir", attributes={"Couleur": "Noir"})

        staff_api.delete(f"/api/v1/bo/variants/{variant.pk}/")

        assert not ProductVariant.objects.filter(pk=variant.pk).exists()

    def test_category_edge_cases(self, staff_api, phones):
        url = "/api/v1/bo/categories/"

        unknown_image = staff_api.post(url, {"name": "Photo", "image_id": 999})
        self_move = staff_api.delete(f"{url}{phones.pk}/?move_to={phones.pk}")
        icon = staff_api.patch(f"{url}{phones.pk}/", {"icon": "camera", "image_id": None}).json()

        assert unknown_image.json()["code"] == "unknown_images"
        assert self_move.status_code == 400
        assert icon["icon"] == "camera"

    def test_unknown_resources(self, staff_api):
        assert staff_api.get(f"{PRODUCTS}999/").status_code == 404
        assert staff_api.patch("/api/v1/bo/variants/999/", {"sku": "X"}).status_code == 404
        assert staff_api.patch("/api/v1/bo/reviews/999/", {"status": "hidden"}).status_code == 404
        assert staff_api.patch("/api/v1/bo/categories/999/", {"name": "X"}).status_code == 404
