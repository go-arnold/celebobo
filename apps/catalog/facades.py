from collections.abc import Sequence
from dataclasses import dataclass, replace

from django.db import transaction

from apps.catalog.domain.backoffice import (
    AdminCategory,
    AdminProductDetail,
    AdminProductRow,
    AdminReview,
    LowStockItem,
    ProductStats,
    StockMovementView,
)
from apps.catalog.domain.enums import ReviewStatus, StockReason
from apps.catalog.domain.errors import CategoryNotFound, ReviewNotFound, VariantNotFound
from apps.catalog.domain.events import (
    CategoryChanged,
    FavoriteAdded,
    FavoriteRemoved,
    ProductChanged,
    ProductRemoved,
    ReviewPosted,
    StockLow,
)
from apps.catalog.domain.management import (
    BackofficeProductFilters,
    BulkAction,
    BulkProductAction,
    CategoryChanges,
    CategoryDraft,
    ProductChanges,
    ProductDraft,
    ReviewFilters,
    StockAdjustment,
    VariantChanges,
    VariantDraft,
)
from apps.catalog.domain.queries import PostReview, ProductQuery, StockLine, StockSource
from apps.catalog.domain.read_models import (
    CategoryView,
    Facets,
    PricedLine,
    ProductCard,
    ProductDetail,
    ReviewEligibility,
    ReviewSummary,
    ReviewView,
    Suggestion,
)
from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.repositories import (
    CategoryAdminRepository,
    ProductAdminRepository,
    ReviewAdminRepository,
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
    ReviewSelector,
    StockSelector,
    to_review_view,
)
from apps.catalog.services.contracts import RelatedProducts
from apps.catalog.services.engagement import FavoriteService, ReviewService
from apps.catalog.services.inventory import InventoryService
from apps.catalog.services.management import (
    ADMIN_SOURCE,
    CategoryAdminService,
    ProductAdminService,
    ReviewModerationService,
    StockAdjustmentService,
    VariantAdminService,
    ensure_product,
)
from apps.catalog.services.search import CatalogSearchService
from core.cache import VersionedCache, cache_key
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


class CatalogCache(VersionedCache):
    pass


@dataclass(frozen=True, slots=True)
class ProductPage:
    cards: list[ProductCard]
    total: int


@dataclass(frozen=True, slots=True)
class ReviewPage:
    reviews: list[ReviewView]
    total: int
    summary: ReviewSummary


@logged_facade
class CatalogFacade:
    def __init__(
        self,
        *,
        search: CatalogSearchService,
        cards: ProductCardSelector,
        details: ProductDetailSelector,
        categories: CategorySelector,
        favorites: FavoriteSelector,
        related: RelatedProducts,
        cache: CatalogCache,
        related_limit: int,
        suggestion_limit: int,
    ) -> None:
        self._search = search
        self._cards = cards
        self._details = details
        self._categories = categories
        self._favorites = favorites
        self._related = related
        self._cache = cache
        self._related_limit = related_limit
        self._suggestion_limit = suggestion_limit

    def categories(self) -> list[CategoryView]:
        return self._cache.get_or_set("categories", self._categories.active)

    def category(self, slug: str) -> CategoryView:
        return self._cache.get_or_set(
            cache_key("category", slug), lambda: self._categories.by_slug(slug)
        )

    def browse(self, actor: Actor, query: ProductQuery) -> ProductPage:
        normalized = self._search.normalize(query)
        page = self._cache.get_or_set(
            cache_key("search", normalized), lambda: self._search.search(normalized)
        )
        return ProductPage(cards=self._hydrate(actor, page.ids), total=page.total)

    def facets(self, query: ProductQuery) -> Facets:
        normalized = self._search.normalize(query)
        return self._cache.get_or_set(
            cache_key("facets", normalized), lambda: self._search.facets(normalized)
        )

    def product(self, actor: Actor, slug: str) -> ProductDetail:
        detail = self._cache.get_or_set(
            cache_key("product", slug), lambda: self._details.by_slug(slug)
        )
        favorites = self._favorite_ids(actor, (detail.card.id,))
        return replace(detail, card=_flag(detail.card, favorites))

    def related(self, actor: Actor, slug: str) -> list[ProductCard]:
        product_id = self._details.id_for(slug)
        ids = self._cache.get_or_set(
            cache_key("related", product_id),
            lambda: self._related.related(product_id, limit=self._related_limit),
        )
        return self._hydrate(actor, ids)

    def suggest(self, text: str) -> list[Suggestion]:
        ids = self._cache.get_or_set(
            cache_key("suggest", text.lower()),
            lambda: self._search.suggest(text, limit=self._suggestion_limit),
        )
        return [
            Suggestion(
                id=card.id,
                slug=card.slug,
                name=card.name,
                category=card.category.name,
                image=card.image,
                current_price=card.current_price,
            )
            for card in self._cached_cards(ids)
        ]

    def cards_for(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]:
        return self._hydrate(actor, ids)

    def _hydrate(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]:
        favorites = self._favorite_ids(actor, ids)
        return [_flag(card, favorites) for card in self._cached_cards(ids)]

    def _cached_cards(self, ids: Sequence[int]) -> list[ProductCard]:
        return self._cache.get_or_set(
            cache_key("cards", tuple(ids)), lambda: self._cards.cards(ids)
        )

    def _favorite_ids(self, actor: Actor, ids: Sequence[int]) -> frozenset[int]:
        if actor.user_id is None or not ids:
            return frozenset()
        return self._favorites.favorite_ids(actor.user_id, ids)


@logged_facade
class ReviewFacade:
    def __init__(
        self,
        *,
        reviews: ReviewService,
        selector: ReviewSelector,
        details: ProductDetailSelector,
        publisher: EventPublisher,
    ) -> None:
        self._reviews = reviews
        self._selector = selector
        self._details = details
        self._publisher = publisher

    def page(self, slug: str, *, offset: int, limit: int) -> ReviewPage:
        product_id = self._details.id_for(slug)
        reviews, total = self._selector.page(product_id, offset=offset, limit=limit)
        return ReviewPage(reviews, total, self._selector.summary(product_id))

    def eligibility(self, actor: Actor, slug: str) -> ReviewEligibility:
        product_id = self._details.id_for(slug)
        if actor.user_id is None:
            return ReviewEligibility(can_review=False, reason=Unauthenticated.default_code)
        return self._reviews.eligibility(actor.user_id, product_id)

    def post(self, actor: Actor, slug: str, command: PostReview) -> tuple[ReviewView, bool]:
        user_id = _user_id(actor)
        product_id = self._details.id_for(slug)
        with transaction.atomic():
            review, created = self._reviews.post(user_id, product_id, command)
            self._publisher.publish(
                ReviewPosted(
                    product_id=product_id,
                    review_id=review.pk,
                    rating=review.rating,
                    created=created,
                    actor_id=user_id,
                )
            )
            self._publisher.publish(ProductChanged(product_id=product_id, actor_id=user_id))
        return to_review_view(review), created


@logged_facade
class FavoriteFacade:
    def __init__(
        self,
        *,
        favorites: FavoriteService,
        selector: FavoriteSelector,
        catalog: CatalogFacade,
        publisher: EventPublisher,
    ) -> None:
        self._favorites = favorites
        self._selector = selector
        self._catalog = catalog
        self._publisher = publisher

    def page(self, actor: Actor, *, offset: int, limit: int) -> ProductPage:
        ids, total = self._selector.page(_user_id(actor), offset=offset, limit=limit)
        return ProductPage(cards=self._catalog.cards_for(actor, ids), total=total)

    def add(self, actor: Actor, product_id: int) -> ProductCard:
        user_id = _user_id(actor)
        with transaction.atomic():
            if self._favorites.add(user_id, product_id):
                self._publisher.publish(
                    FavoriteAdded(user_id=user_id, product_id=product_id, actor_id=user_id)
                )
        return self._catalog.cards_for(actor, (product_id,))[0]

    def remove(self, actor: Actor, product_id: int) -> None:
        user_id = _user_id(actor)
        with transaction.atomic():
            if self._favorites.remove(user_id, product_id):
                self._publisher.publish(
                    FavoriteRemoved(user_id=user_id, product_id=product_id, actor_id=user_id)
                )


def _flag(card: ProductCard, favorites: frozenset[int]) -> ProductCard:
    return replace(card, is_favorite=card.id in favorites)


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class InventoryFacade:
    def __init__(
        self, *, inventory: InventoryService, stock: StockRepository, publisher: EventPublisher
    ) -> None:
        self._inventory = inventory
        self._stock = stock
        self._publisher = publisher

    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]:
        return self._inventory.price(lines)

    def reserve(
        self,
        lines: Sequence[StockLine],
        source: StockSource,
        *,
        reason: StockReason = StockReason.ORDER,
    ) -> None:
        with transaction.atomic():
            touched = self._inventory.reserve(lines, source, reason=reason)
            self._announce(touched, source)
            _announce_low(self._publisher, self._stock, sorted(touched))

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None:
        with transaction.atomic():
            self._announce(self._inventory.release(lines, source, reason=reason, note=note), source)

    def record_sales(self, product_id: int, quantity: int, *, actor_id: int | None) -> None:
        with transaction.atomic():
            self._stock.count_sales(product_id, quantity)
            self._publisher.publish(ProductChanged(product_id=product_id, actor_id=actor_id))

    def _announce(self, product_ids: set[int], source: StockSource) -> None:
        for product_id in sorted(product_ids):
            self._publisher.publish(ProductChanged(product_id=product_id, actor_id=source.actor_id))


@dataclass(frozen=True, slots=True)
class AdminProductPage:
    products: list[AdminProductRow]
    total: int
    stats: ProductStats


@logged_facade
class ProductAdminFacade:
    def __init__(
        self,
        *,
        products: ProductAdminService,
        variants: VariantAdminService,
        stock: StockAdjustmentService,
        repository: ProductAdminRepository,
        stock_repository: StockRepository,
        selector: AdminProductSelector,
        stock_selector: StockSelector,
        publisher: EventPublisher,
    ) -> None:
        self._products = products
        self._variants = variants
        self._stock = stock
        self._repository = repository
        self._stock_repository = stock_repository
        self._selector = selector
        self._stock_selector = stock_selector
        self._publisher = publisher

    def page(
        self, filters: BackofficeProductFilters, *, offset: int, limit: int
    ) -> AdminProductPage:
        return AdminProductPage(*self._selector.page(filters, offset=offset, limit=limit))

    def detail(self, product_id: int) -> AdminProductDetail:
        return self._selector.detail(product_id)

    def create(self, actor: Actor, draft: ProductDraft) -> AdminProductDetail:
        with transaction.atomic():
            product = self._products.create(draft)
            if draft.stock:
                self._stock_repository.move(
                    product,
                    None,
                    delta=draft.stock,
                    reason=StockReason.INVENTORY,
                    source=_admin_source(actor, product.pk),
                    note="Stock initial",
                )
            self._changed(actor, product.pk)
        return self._selector.detail(product.pk)

    def update(self, actor: Actor, product_id: int, changes: ProductChanges) -> AdminProductDetail:
        with transaction.atomic():
            self._products.update(self._locked(product_id), changes)
            self._changed(actor, product_id)
        return self._selector.detail(product_id)

    def trash(self, actor: Actor, product_id: int) -> None:
        with transaction.atomic():
            self._products.trash(self._locked(product_id))
            self._publisher.publish(ProductRemoved(product_id=product_id, actor_id=actor.user_id))

    def restore(self, actor: Actor, product_id: int) -> AdminProductDetail:
        with transaction.atomic():
            self._products.restore(self._locked(product_id))
            self._changed(actor, product_id)
        return self._selector.detail(product_id)

    def duplicate(self, actor: Actor, product_id: int) -> AdminProductDetail:
        with transaction.atomic():
            copy = self._products.duplicate(self._locked(product_id))
            self._changed(actor, copy.pk)
        return self._selector.detail(copy.pk)

    def bulk(self, actor: Actor, command: BulkProductAction) -> list[int]:
        with transaction.atomic():
            touched = self._products.bulk(command)
            for product_id in touched:
                if command.action is BulkAction.TRASH:
                    self._publisher.publish(
                        ProductRemoved(product_id=product_id, actor_id=actor.user_id)
                    )
                else:
                    self._changed(actor, product_id)
        return touched

    def add_variant(self, actor: Actor, product_id: int, draft: VariantDraft) -> AdminProductDetail:
        with transaction.atomic():
            product = self._locked(product_id)
            self._variants.add(product, draft, _admin_source(actor, product_id))
            self._changed(actor, product_id)
        return self._selector.detail(product_id)

    def update_variant(
        self, actor: Actor, variant_id: int, changes: VariantChanges
    ) -> AdminProductDetail:
        with transaction.atomic():
            variant = self._variant(variant_id)
            self._locked(variant.product_id)
            self._variants.update(variant, changes)
            self._changed(actor, variant.product_id)
        return self._selector.detail(variant.product_id)

    def remove_variant(self, actor: Actor, variant_id: int) -> AdminProductDetail:
        with transaction.atomic():
            variant = self._variant(variant_id)
            product_id = variant.product_id
            self._locked(product_id)
            self._variants.remove(variant)
            self._changed(actor, product_id)
        return self._selector.detail(product_id)

    def adjust_stock(
        self, actor: Actor, product_id: int, command: StockAdjustment
    ) -> StockMovementView:
        with transaction.atomic():
            product = self._locked(product_id)
            movement = self._stock.adjust(product, command, _admin_source(actor, product_id))
            self._changed(actor, product_id)
            if movement.delta < 0:
                _announce_low(self._publisher, self._stock_repository, [product_id])
        return self._stock_selector.movement(movement.pk)

    def movements(
        self, product_id: int, *, offset: int, limit: int
    ) -> tuple[list[StockMovementView], int]:
        ensure_product(self._repository.get(product_id))
        return self._stock_selector.movements(product_id, offset=offset, limit=limit)

    def alerts(self) -> list[LowStockItem]:
        return self._stock_selector.alerts()

    def _locked(self, product_id: int) -> Product:
        return ensure_product(self._repository.get(product_id, for_update=True))

    def _variant(self, variant_id: int) -> ProductVariant:
        variant = self._repository.variant(variant_id, for_update=True)
        if variant is None:
            raise VariantNotFound
        return variant

    def _changed(self, actor: Actor, product_id: int) -> None:
        self._publisher.publish(ProductChanged(product_id=product_id, actor_id=actor.user_id))


@logged_facade
class CategoryAdminFacade:
    def __init__(
        self,
        *,
        categories: CategoryAdminService,
        repository: CategoryAdminRepository,
        selector: AdminCategorySelector,
        publisher: EventPublisher,
    ) -> None:
        self._categories = categories
        self._repository = repository
        self._selector = selector
        self._publisher = publisher

    def all(self) -> list[AdminCategory]:
        return self._selector.all()

    def create(self, actor: Actor, draft: CategoryDraft) -> AdminCategory:
        with transaction.atomic():
            category = self._categories.create(draft)
            self._changed(actor, category.pk)
        return self._selector.one(category.pk)

    def update(self, actor: Actor, category_id: int, changes: CategoryChanges) -> AdminCategory:
        with transaction.atomic():
            self._categories.update(self._locked(category_id), changes)
            self._changed(actor, category_id)
        return self._selector.one(category_id)

    def delete(self, actor: Actor, category_id: int, move_to: int | None) -> None:
        with transaction.atomic():
            moved = self._categories.delete(self._locked(category_id), move_to)
            self._changed(actor, category_id)
            if move_to is not None:
                self._changed(actor, move_to)
            for product_id in moved:
                self._publisher.publish(
                    ProductChanged(product_id=product_id, actor_id=actor.user_id)
                )

    def reorder(self, actor: Actor, ids: Sequence[int]) -> list[AdminCategory]:
        with transaction.atomic():
            self._categories.reorder(ids)
            for category_id in ids:
                self._changed(actor, category_id)
        return self._selector.all()

    def _locked(self, category_id: int) -> Category:
        category = self._repository.get(category_id, for_update=True)
        if category is None:
            raise CategoryNotFound
        return category

    def _changed(self, actor: Actor, category_id: int) -> None:
        self._publisher.publish(CategoryChanged(category_id=category_id, actor_id=actor.user_id))


@logged_facade
class ReviewModerationFacade:
    def __init__(
        self,
        *,
        moderation: ReviewModerationService,
        repository: ReviewAdminRepository,
        selector: AdminReviewSelector,
        publisher: EventPublisher,
    ) -> None:
        self._moderation = moderation
        self._repository = repository
        self._selector = selector
        self._publisher = publisher

    def page(
        self, filters: ReviewFilters, *, offset: int, limit: int
    ) -> tuple[list[AdminReview], int]:
        return self._selector.page(filters, offset=offset, limit=limit)

    def moderate(self, actor: Actor, review_id: int, status: ReviewStatus) -> AdminReview:
        with transaction.atomic():
            review = self._repository.get(review_id, for_update=True)
            if review is None:
                raise ReviewNotFound
            self._moderation.moderate(review, status)
            self._publisher.publish(
                ProductChanged(product_id=review.product_id, actor_id=actor.user_id)
            )
        return self._selector.one(review_id)


def _admin_source(actor: Actor, product_id: int) -> StockSource:
    return StockSource(kind=ADMIN_SOURCE, id=product_id, actor_id=actor.user_id)


def _announce_low(
    publisher: EventPublisher, stock: StockRepository, product_ids: Sequence[int]
) -> None:
    for product_id, variant_id, level, threshold in stock.low_levels(product_ids):
        publisher.publish(
            StockLow(product_id=product_id, variant_id=variant_id, stock=level, threshold=threshold)
        )
