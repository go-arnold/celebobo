from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.catalog.api.v1.backoffice_views import (
    AdminBrandViewSet,
    AdminCategoryViewSet,
    AdminDealViewSet,
    AdminProductViewSet,
    AdminReviewViewSet,
    AdminStockViewSet,
    AdminVariantViewSet,
)
from apps.catalog.api.v1.views import (
    BrandViewSet,
    CategoryViewSet,
    FavoriteViewSet,
    ProductViewSet,
    ReviewViewSet,
    SuggestViewSet,
)

router = SimpleRouter(use_regex_path=False)
router.register("brands", BrandViewSet, basename="brand")
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")

backoffice = [
    path(
        "bo/products/",
        AdminProductViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-products",
    ),
    path(
        "bo/products/bulk/", AdminProductViewSet.as_view({"post": "bulk"}), name="bo-products-bulk"
    ),
    path(
        "bo/products/<id:product_id>/",
        AdminProductViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="bo-product",
    ),
    path(
        "bo/products/<id:product_id>/restore/",
        AdminProductViewSet.as_view({"post": "restore"}),
        name="bo-product-restore",
    ),
    path(
        "bo/products/<id:product_id>/duplicate/",
        AdminProductViewSet.as_view({"post": "duplicate"}),
        name="bo-product-duplicate",
    ),
    path(
        "bo/products/<id:product_id>/variants/",
        AdminVariantViewSet.as_view({"post": "create"}),
        name="bo-product-variants",
    ),
    path(
        "bo/variants/<id:variant_id>/",
        AdminVariantViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="bo-variant",
    ),
    path(
        "bo/products/<id:product_id>/stock-adjustments/",
        AdminStockViewSet.as_view({"post": "adjust"}),
        name="bo-stock-adjust",
    ),
    path(
        "bo/products/<id:product_id>/stock-movements/",
        AdminStockViewSet.as_view({"get": "movements"}),
        name="bo-stock-movements",
    ),
    path("bo/stock/alerts/", AdminStockViewSet.as_view({"get": "alerts"}), name="bo-stock-alerts"),
    path(
        "bo/categories/",
        AdminCategoryViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-categories",
    ),
    path(
        "bo/categories/reorder/",
        AdminCategoryViewSet.as_view({"post": "reorder"}),
        name="bo-categories-reorder",
    ),
    path(
        "bo/categories/<id:category_id>/",
        AdminCategoryViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="bo-category",
    ),
    path(
        "bo/brands/",
        AdminBrandViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-brands",
    ),
    path(
        "bo/brands/reorder/",
        AdminBrandViewSet.as_view({"post": "reorder"}),
        name="bo-brands-reorder",
    ),
    path(
        "bo/brands/<id:brand_id>/",
        AdminBrandViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="bo-brand",
    ),
    path("bo/deals/", AdminDealViewSet.as_view({"get": "list", "post": "create"}), name="bo-deals"),
    path(
        "bo/deals/<id:deal_id>/",
        AdminDealViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="bo-deal",
    ),
    path("bo/reviews/", AdminReviewViewSet.as_view({"get": "list"}), name="bo-reviews"),
    path(
        "bo/reviews/<id:review_id>/",
        AdminReviewViewSet.as_view({"patch": "partial_update"}),
        name="bo-review",
    ),
]

urlpatterns = [
    *backoffice,
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
    path("me/favorites/ids/", FavoriteViewSet.as_view({"get": "ids"}), name="favorite-ids"),
    path(
        "me/favorites/<id:product_id>/",
        FavoriteViewSet.as_view({"delete": "destroy"}),
        name="favorite",
    ),
    *router.urls,
]
