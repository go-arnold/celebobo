from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from apps.catalog.domain.enums import Badge, ProductOrdering


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductQuery:
    text: str | None = None
    category: str | None = None
    ids: tuple[int, ...] = ()
    on_sale: bool | None = None
    in_stock: bool | None = None
    badge: Badge | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    ordering: ProductOrdering | None = None
    page: int = 1
    page_size: int = 12
    new_since: datetime | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def effective_ordering(self) -> ProductOrdering:
        if self.ordering is not None:
            return self.ordering
        return ProductOrdering.RELEVANCE if self.text else ProductOrdering.NEWEST

    def without_category(self) -> "ProductQuery":
        return replace(self, category=None)


@dataclass(frozen=True, slots=True, kw_only=True)
class PostReview:
    rating: int
    message: str
