from django.utils import timezone

from apps.catalog.adapters import postgres
from apps.catalog.adapters.media import UploadedMediaUrls
from apps.catalog.adapters.media_references import CatalogMediaReferences
from apps.catalog.conf import catalog_settings
from apps.catalog.facades import (
    CatalogCache,
    CatalogFacade,
    CategoryAdminFacade,
    FavoriteFacade,
    InventoryFacade,
    ProductAdminFacade,
    ReviewFacade,
    ReviewModerationFacade,
)
from apps.catalog.repositories import (
    CategoryAdminRepository,
    FavoriteRepository,
    ProductAdminRepository,
    ProductRepository,
    ReviewAdminRepository,
    ReviewRepository,
    StockRepository,
)
from apps.catalog.selectors import (
    AdminCategorySelector,
    AdminProductSelector,
    AdminReviewSelector,
    CategorySelector,
    FavoriteSelector,
    ProductCardSelector,
    ProductDetailSelector,
    ProductDocumentSelector,
    ReviewSelector,
    StockSelector,
)
from apps.catalog.services.contracts import (
    MediaUrls,
    PurchaseVerifier,
    RelatedProducts,
    SearchEngine,
    SearchIndex,
)
from apps.catalog.services.engagement import FavoriteService, ReviewService
from apps.catalog.services.indexing import ProductIndexer
from apps.catalog.services.inventory import InventoryService
from apps.catalog.services.management import (
    CategoryAdminService,
    ProductAdminService,
    ReviewModerationService,
    StockAdjustmentService,
    VariantAdminService,
)
from apps.catalog.services.search import CatalogSearchService, search_engines, search_indexes
from apps.media.services.references import media_references
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher

ADAPTER_MODULES = (postgres,)


def register(container: Container) -> None:
    media_references.add("catalog", CatalogMediaReferences, replace=True)
    container.register(
        SearchEngine, lambda _: search_engines.create(catalog_settings().search_engine)
    )
    container.register(
        SearchIndex, lambda _: search_indexes.create(catalog_settings().search_index)
    )
    container.register(RelatedProducts, lambda _: postgres.SameCategoryRelated())
    container.register(PurchaseVerifier, lambda _: postgres.NoPurchaseHistory())
    container.register(
        CatalogCache, lambda _: CatalogCache("catalog", ttl=catalog_settings().cache_ttl)
    )
    container.register(ProductIndexer, _indexer, lifetime=Lifetime.TRANSIENT)
    container.register(CatalogFacade, _catalog_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ReviewFacade, _review_facade, lifetime=Lifetime.TRANSIENT)
    container.register(FavoriteFacade, _favorite_facade, lifetime=Lifetime.TRANSIENT)
    container.register(InventoryFacade, _inventory_facade, lifetime=Lifetime.TRANSIENT)
    container.register(MediaUrls, lambda _: UploadedMediaUrls())
    container.register(ProductAdminFacade, _product_admin_facade, lifetime=Lifetime.TRANSIENT)
    container.register(CategoryAdminFacade, _category_admin_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ReviewModerationFacade, _moderation_facade, lifetime=Lifetime.TRANSIENT)


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
    stock = StockRepository()
    return InventoryFacade(
        inventory=InventoryService(stock),
        stock=stock,
        publisher=container.resolve(EventPublisher),
    )


def _product_admin_facade(container: Container) -> ProductAdminFacade:
    products = ProductAdminRepository()
    stock = StockRepository()
    media = container.resolve(MediaUrls)
    return ProductAdminFacade(
        products=ProductAdminService(
            products, CategoryAdminRepository(), media, today=timezone.localdate
        ),
        variants=VariantAdminService(products, stock, media),
        stock=StockAdjustmentService(products, stock),
        repository=products,
        stock_repository=stock,
        selector=AdminProductSelector(),
        stock_selector=StockSelector(),
        publisher=container.resolve(EventPublisher),
    )


def _category_admin_facade(container: Container) -> CategoryAdminFacade:
    categories = CategoryAdminRepository()
    return CategoryAdminFacade(
        categories=CategoryAdminService(categories, container.resolve(MediaUrls)),
        repository=categories,
        selector=AdminCategorySelector(),
        publisher=container.resolve(EventPublisher),
    )


def _moderation_facade(container: Container) -> ReviewModerationFacade:
    return ReviewModerationFacade(
        moderation=ReviewModerationService(ReviewAdminRepository(), ProductRepository()),
        repository=ReviewAdminRepository(),
        selector=AdminReviewSelector(),
        publisher=container.resolve(EventPublisher),
    )
