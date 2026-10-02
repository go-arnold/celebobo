from core.authz.catalog import permission_catalog
from core.domain.actor import Role

REVIEWS_CREATE = "reviews.create"
FAVORITES_MANAGE = "favorites.manage"

permission_catalog.grant(Role.CLIENT, REVIEWS_CREATE, FAVORITES_MANAGE)
