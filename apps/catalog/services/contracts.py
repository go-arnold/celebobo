from collections.abc import Sequence
from typing import Protocol

from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import Facets, ProductDocument, SearchPage
from apps.catalog.models import Product, Review


class SearchEngine(Protocol):
    def search(self, query: ProductQuery) -> SearchPage: ...

    def facets(self, query: ProductQuery) -> Facets: ...

    def suggest(self, text: str, *, limit: int) -> tuple[int, ...]: ...


class SearchIndex(Protocol):
    def configure(self) -> None: ...

    def upsert(self, documents: Sequence[ProductDocument]) -> None: ...

    def remove(self, product_ids: Sequence[int]) -> None: ...


class RelatedProducts(Protocol):
    def related(self, product_id: int, *, limit: int) -> tuple[int, ...]: ...


class PurchaseVerifier(Protocol):
    def has_received(self, user_id: int, product_id: int) -> bool: ...


class ProductStore(Protocol):
    def visible(self, product_id: int) -> Product | None: ...

    def refresh_rating(self, product_id: int) -> None: ...


class ReviewStore(Protocol):
    def for_user(self, product_id: int, user_id: int) -> Review | None: ...

    def upsert(
        self, *, product_id: int, user_id: int, rating: int, message: str, verified: bool
    ) -> tuple[Review, bool]: ...


class FavoriteStore(Protocol):
    def add(self, user_id: int, product_id: int) -> bool: ...

    def remove(self, user_id: int, product_id: int) -> bool: ...
