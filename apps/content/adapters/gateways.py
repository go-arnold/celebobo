from decimal import Decimal

from apps.catalog.domain.enums import ProductOrdering
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import CategoryView, ProductCard
from apps.catalog.facades import CatalogFacade
from apps.content.domain.read_models import ShippingInfo
from apps.orders.conf import order_settings
from core.container import container
from core.domain.actor import Actor


class CatalogShowcase:
    def deals(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor,
            ProductQuery(on_sale=True, ordering=ProductOrdering.BEST_SELLING, page_size=limit),
        )

    def newest(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(actor, ProductQuery(ordering=ProductOrdering.NEWEST, page_size=limit))

    def best_sellers(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor, ProductQuery(ordering=ProductOrdering.BEST_SELLING, page_size=limit)
        )

    def categories(self) -> list[CategoryView]:
        return container.resolve(CatalogFacade).categories()

    def in_category(self, actor: Actor, slug: str, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor,
            ProductQuery(category=slug, ordering=ProductOrdering.BEST_SELLING, page_size=limit),
        )

    @staticmethod
    def _browse(actor: Actor, query: ProductQuery) -> list[ProductCard]:
        return list(container.resolve(CatalogFacade).browse(actor, query).cards)


class OrdersShipping:
    def shipping(self) -> ShippingInfo:
        rules = order_settings().shipping_rules
        return ShippingInfo(
            free_threshold=Decimal(rules.free_threshold), flat_fee=Decimal(rules.flat_fee)
        )
