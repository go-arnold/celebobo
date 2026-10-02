from collections.abc import Sequence
from dataclasses import dataclass, replace

from django.db import transaction

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.events import (
    FavoriteAdded,
    FavoriteRemoved,
    ProductChanged,
    ReviewPosted,
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
from apps.catalog.selectors import (
    CategorySelector,
    FavoriteSelector,
    ProductCardSelector,
    ProductDetailSelector,
    ReviewSelector,
    to_review_view,
)
from apps.catalog.services.contracts import RelatedProducts
from apps.catalog.services.engagement import FavoriteService, ReviewService
from apps.catalog.services.inventory import InventoryService
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
    def __init__(self, *, inventory: InventoryService, publisher: EventPublisher) -> None:
        self._inventory = inventory
        self._publisher = publisher

    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]:
        return self._inventory.price(lines)

    def reserve(self, lines: Sequence[StockLine], source: StockSource) -> None:
        with transaction.atomic():
            self._announce(self._inventory.reserve(lines, source), source)

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None:
        with transaction.atomic():
            self._announce(self._inventory.release(lines, source, reason=reason, note=note), source)

    def _announce(self, product_ids: set[int], source: StockSource) -> None:
        for product_id in sorted(product_ids):
            self._publisher.publish(ProductChanged(product_id=product_id, actor_id=source.actor_id))
