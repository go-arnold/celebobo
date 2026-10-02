from django.utils import timezone

from apps.catalog.adapters import database, meilisearch
from apps.catalog.conf import catalog_settings
from apps.catalog.facades import (
    CatalogCache,
    CatalogFacade,
    FavoriteFacade,
    InventoryFacade,
    ReviewFacade,
)
from apps.catalog.repositories import (
    FavoriteRepository,
    ProductRepository,
    ReviewRepository,
    StockRepository,
)
from apps.catalog.selectors import (
    CategorySelector,
    FavoriteSelector,
    ProductCardSelector,
    ProductDetailSelector,
    ProductDocumentSelector,
    ReviewSelector,
)
from apps.catalog.services.contracts import (
    PurchaseVerifier,
    RelatedProducts,
    SearchEngine,
    SearchIndex,
)
from apps.catalog.services.engagement import FavoriteService, ReviewService
from apps.catalog.services.indexing import ProductIndexer
from apps.catalog.services.inventory import InventoryService
from apps.catalog.services.search import (
    CatalogSearchService,
    ResilientSearch,
    search_engines,
    search_indexes,
)
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher

DATABASE_ENGINE = "database"
ADAPTER_MODULES = (database, meilisearch)


def register(container: Container) -> None:
    container.register(SearchEngine, lambda _: _search_engine())
    container.register(
        SearchIndex, lambda _: search_indexes.create(catalog_settings().search_index)
    )
    container.register(RelatedProducts, lambda _: database.SameCategoryRelated())
    container.register(PurchaseVerifier, lambda _: database.NoPurchaseHistory())
    container.register(
        CatalogCache, lambda _: CatalogCache("catalog", ttl=catalog_settings().cache_ttl)
    )
    container.register(ProductIndexer, _indexer, lifetime=Lifetime.TRANSIENT)
    container.register(CatalogFacade, _catalog_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ReviewFacade, _review_facade, lifetime=Lifetime.TRANSIENT)
    container.register(FavoriteFacade, _favorite_facade, lifetime=Lifetime.TRANSIENT)
    container.register(InventoryFacade, _inventory_facade, lifetime=Lifetime.TRANSIENT)


def _search_engine() -> SearchEngine:
    name = catalog_settings().search_engine
    engine = search_engines.create(name)
    if name == DATABASE_ENGINE:
        return engine
    return ResilientSearch(primary=engine, fallback=search_engines.create(DATABASE_ENGINE))


def _indexer(container: Container) -> ProductIndexer:
    return ProductIndexer(container.resolve(SearchIndex), ProductDocumentSelector())


def _cards() -> ProductCardSelector:
    return ProductCardSelector(now=timezone.now(), new_for_days=catalog_settings().new_product_days)


def _catalog_facade(container: Container) -> CatalogFacade:
    settings = catalog_settings()
    cards = _cards()
    categories = CategorySelector()
    return CatalogFacade(
        search=CatalogSearchService(
            container.resolve(SearchEngine),
            category_names=categories.names,
            clock=timezone.now,
            new_for_days=settings.new_product_days,
            max_page_size=settings.max_page_size,
        ),
        cards=cards,
        details=ProductDetailSelector(cards),
        categories=categories,
        favorites=FavoriteSelector(),
        related=container.resolve(RelatedProducts),
        cache=container.resolve(CatalogCache),
        related_limit=settings.related_limit,
        suggestion_limit=settings.suggestion_limit,
    )


def _review_facade(container: Container) -> ReviewFacade:
    products = ProductRepository()
    return ReviewFacade(
        reviews=ReviewService(products, ReviewRepository(), container.resolve(PurchaseVerifier)),
        selector=ReviewSelector(),
        details=ProductDetailSelector(_cards()),
        publisher=container.resolve(EventPublisher),
    )


def _favorite_facade(container: Container) -> FavoriteFacade:
    return FavoriteFacade(
        favorites=FavoriteService(FavoriteRepository(), ProductRepository()),
        selector=FavoriteSelector(),
        catalog=container.resolve(CatalogFacade),
        publisher=container.resolve(EventPublisher),
    )


def _inventory_facade(container: Container) -> InventoryFacade:
    return InventoryFacade(
        inventory=InventoryService(StockRepository()),
        publisher=container.resolve(EventPublisher),
    )
