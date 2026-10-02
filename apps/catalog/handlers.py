from apps.catalog.domain.events import (
    CategoryChanged,
    ProductChanged,
    ProductRemoved,
    ReviewPosted,
)
from apps.catalog.facades import CatalogCache
from apps.catalog.services.indexing import ProductIndexer
from core.container import container
from core.events.base import DomainEvent
from core.events.bus import event_bus


@event_bus.on(ProductChanged, ProductRemoved, CategoryChanged, ReviewPosted)
def invalidate_catalog_cache(_: DomainEvent) -> None:
    container.resolve(CatalogCache).bump()


@event_bus.on(ProductChanged, background=True)
def index_product(event: ProductChanged) -> None:
    container.resolve(ProductIndexer).sync([event.product_id])


@event_bus.on(ProductRemoved, background=True)
def unindex_product(event: ProductRemoved) -> None:
    container.resolve(ProductIndexer).remove([event.product_id])


@event_bus.on(CategoryChanged, background=True)
def reindex_category(event: CategoryChanged) -> None:
    container.resolve(ProductIndexer).sync_category(event.category_id)
