from apps.catalog.domain.events import (
    BrandChanged,
    CategoryChanged,
    ProductChanged,
    ProductRemoved,
    ProductsChanged,
    ProductsRemoved,
    ReviewPosted,
)
from apps.catalog.facades import CatalogCache
from apps.catalog.services.indexing import ProductIndexer
from core.container import container
from core.events.base import DomainEvent
from core.events.bus import event_bus


@event_bus.on(
    ProductChanged,
    ProductsChanged,
    ProductRemoved,
    ProductsRemoved,
    CategoryChanged,
    BrandChanged,
    ReviewPosted,
)
def invalidate_catalog_cache(_: DomainEvent) -> None:
    container.resolve(CatalogCache).bump()


@event_bus.on(ProductChanged, ProductsChanged)
def index_products(event: ProductChanged | ProductsChanged) -> None:
    container.resolve(ProductIndexer).sync(event.product_ids)


@event_bus.on(ProductRemoved, ProductsRemoved)
def unindex_products(event: ProductRemoved | ProductsRemoved) -> None:
    container.resolve(ProductIndexer).remove(event.product_ids)


@event_bus.on(CategoryChanged, background=True)
def reindex_category(event: CategoryChanged) -> None:
    container.resolve(ProductIndexer).sync_category(event.category_id)
