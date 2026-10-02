from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalog.api.v1.views import (
    CategoryViewSet,
    FavoriteViewSet,
    ProductViewSet,
    ReviewViewSet,
    SuggestViewSet,
)

router = SimpleRouter(use_regex_path=False)
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")

urlpatterns = [
    path("search/suggest/", SuggestViewSet.as_view({"get": "list"}), name="search-suggest"),
    path(
        "products/<slug:slug>/reviews/",
        ReviewViewSet.as_view({"get": "list", "post": "create"}),
        name="product-reviews",
    ),
    path(
        "products/<slug:slug>/reviews/eligibility/",
        ReviewViewSet.as_view({"get": "eligibility"}),
        name="product-review-eligibility",
    ),
    path(
        "me/favorites/",
        FavoriteViewSet.as_view({"get": "list", "post": "create"}),
        name="favorites",
    ),
    path(
        "me/favorites/<int:product_id>/",
        FavoriteViewSet.as_view({"delete": "destroy"}),
        name="favorite",
    ),
    *router.urls,
]
