from collections.abc import Sequence

from apps.catalog.domain.deals import DealOfTheDay
from apps.catalog.domain.enums import ProductOrdering
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import BrandView, CatalogSitemap, CategoryView, ProductCard
from apps.catalog.facades import CatalogFacade
from apps.content.domain.read_models import ShippingInfo
from apps.loyalty.domain.settings import Programmes
from apps.loyalty.facades import LoyaltyFacade
from apps.orders.conf import order_settings
from core.container import container
from core.domain.actor import Actor


class CatalogShowcase:
    def deal(self, actor: Actor) -> DealOfTheDay | None:
        return container.resolve(CatalogFacade).deal_of_the_day(actor)

    def deals(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor,
            ProductQuery(on_sale=True, ordering=ProductOrdering.BEST_SELLING, page_size=limit),
        )

    def cards(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]:
        return container.resolve(CatalogFacade).cards_for(actor, ids)

    def newest(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(actor, ProductQuery(ordering=ProductOrdering.NEWEST, page_size=limit))

    def best_sellers(self, actor: Actor, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor, ProductQuery(ordering=ProductOrdering.BEST_SELLING, page_size=limit)
        )

    def categories(self) -> list[CategoryView]:
        return container.resolve(CatalogFacade).categories()

    def brands(self) -> list[BrandView]:
        return container.resolve(CatalogFacade).featured_brands()

    def in_category(self, actor: Actor, slug: str, *, limit: int) -> list[ProductCard]:
        return self._browse(
            actor,
            ProductQuery(category=slug, ordering=ProductOrdering.BEST_SELLING, page_size=limit),
        )

    def sitemap(self) -> CatalogSitemap:
        return container.resolve(CatalogFacade).sitemap()

    def product_locations(self, product_ids: Sequence[int]) -> list[tuple[str, str]]:
        return container.resolve(CatalogFacade).product_locations(product_ids)

    def category_slug(self, category_id: int) -> str | None:
        return container.resolve(CatalogFacade).category_slug(category_id)

    @staticmethod
    def _browse(actor: Actor, query: ProductQuery) -> list[ProductCard]:
        return list(container.resolve(CatalogFacade).browse(actor, query).cards)


class LoyaltyProgrammes:
    def programmes(self) -> Programmes:
        return container.resolve(LoyaltyFacade).programmes()


class OrdersShipping:
    def shipping(self) -> ShippingInfo:
        rules = order_settings().shipping_rules
        return ShippingInfo(free_threshold=rules.free_threshold, flat_fee=rules.flat_fee)
