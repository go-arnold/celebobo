from core.authz.catalog import permission_catalog
from core.domain.actor import Role

REVIEWS_CREATE = "reviews.create"
FAVORITES_MANAGE = "favorites.manage"

permission_catalog.grant(Role.CLIENT, REVIEWS_CREATE, FAVORITES_MANAGE)

PRODUCTS_VIEW = "products.view"
PRODUCTS_MANAGE = "products.manage"
STOCK_ADJUST = "stock.adjust"
CATEGORIES_MANAGE = "categories.manage"
REVIEWS_MODERATE = "reviews.moderate"

permission_catalog.grant(Role.RESELLER, PRODUCTS_VIEW)
permission_catalog.grant(
    Role.MANAGER, PRODUCTS_MANAGE, STOCK_ADJUST, CATEGORIES_MANAGE, REVIEWS_MODERATE
)
