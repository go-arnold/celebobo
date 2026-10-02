from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.catalog.domain.events import FavoriteAdded, ProductChanged, ReviewPosted
from apps.catalog.models import Favorite, Product
from apps.catalog.tests.factories import ProductFactory, ReviewFactory

pytestmark = pytest.mark.django_db

REVIEW = {"rating": 4, "message": "Très bon téléphone, autonomie correcte."}


@pytest.fixture
def product() -> Product:
    return ProductFactory.create(slug="galaxy-s24")


def reviews_url(product: Product) -> str:
    return f"/api/v1/products/{product.slug}/reviews/"


class TestReviews:
    def test_list_with_summary(self, api: APIClient, product):
        ReviewFactory.create(
            product=product, user=UserFactory.create(first_name="Jean", last_name="Kabila")
        )
        ReviewFactory.create(product=product, user=UserFactory.create(), rating=3)
        ReviewFactory.create(product=product, user=UserFactory.create(), status="hidden")

        body = api.get(reviews_url(product)).json()

        assert body["meta"]["count"] == 2
        assert body["meta"]["summary"] == {
            "average": "4.00",
            "count": 2,
            "distribution": {"5": 1, "4": 0, "3": 1, "2": 0, "1": 0},
        }
        assert {review["author"]["name"] for review in body["results"]} >= {"Jean K."}

    def test_only_buyers_can_review(self, as_user, shopper, product):
        response = as_user(shopper).post(reviews_url(product), REVIEW)

        assert response.status_code == 422
        assert response.json()["code"] == "review_not_allowed"

    def test_buyer_posts_then_updates(self, as_user, shopper, product, purchases, published_events):
        purchases.received.add((shopper.pk, product.pk))
        api = as_user(shopper)

        created = api.post(reviews_url(product), REVIEW)
        updated = api.post(reviews_url(product), {**REVIEW, "rating": 2})

        assert created.status_code == 201
        assert created.json()["verified"] is True
        assert updated.status_code == 200
        product.refresh_from_db()
        assert product.rating_avg == Decimal("2.00")
        assert product.reviews_count == 1
        assert [event.created for event in published_events.of_type(ReviewPosted)] == [True, False]
        assert len(published_events.of_type(ProductChanged)) == 2

    def test_validation(self, as_user, shopper, product, purchases):
        purchases.received.add((shopper.pk, product.pk))

        response = as_user(shopper).post(reviews_url(product), {"rating": 6, "message": "court"})

        assert set(response.json()["errors"]) == {"rating", "message"}

    def test_anonymous_cannot_post(self, api: APIClient, product):
        assert api.post(reviews_url(product), REVIEW).status_code == 401

    def test_eligibility(self, api: APIClient, as_user, shopper, product, purchases):
        url = f"{reviews_url(product)}eligibility/"

        assert api.get(url).json() == {
            "can_review": False,
            "reason": "not_authenticated",
            "existing_review_id": None,
        }
        purchases.received.add((shopper.pk, product.pk))
        assert as_user(shopper).get(url).json()["can_review"] is True

    def test_unknown_product(self, api: APIClient):
        assert api.get("/api/v1/products/nope/reviews/").status_code == 404


class TestFavorites:
    url = "/api/v1/me/favorites/"

    def test_add_list_remove(self, as_user, shopper, product, published_events):
        api = as_user(shopper)

        added = api.post(self.url, {"product_id": product.pk})
        again = api.post(self.url, {"product_id": product.pk})
        listed = api.get(self.url).json()
        removed = api.delete(f"{self.url}{product.pk}/")

        assert added.status_code == again.status_code == 201
        assert added.json()["is_favorite"] is True
        assert len(published_events.of_type(FavoriteAdded)) == 1
        assert [card["id"] for card in listed["results"]] == [product.pk]
        assert removed.status_code == 204
        assert not Favorite.objects.exists()

    def test_hidden_products_cannot_be_favorited(self, as_user, shopper, product):
        Product.objects.filter(pk=product.pk).update(is_active=False)

        response = as_user(shopper).post(self.url, {"product_id": product.pk})

        assert response.status_code == 404

    def test_requires_authentication(self, api: APIClient):
        assert api.get(self.url).status_code == 401
