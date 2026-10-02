from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.catalog.domain.enums import Badge, CategoryIcon


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryRef:
    id: int
    slug: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryView:
    id: int
    slug: str
    name: str
    description: str
    image: str
    icon: CategoryIcon
    products_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductCard:
    id: int
    slug: str
    name: str
    description: str
    category: CategoryRef
    image: str
    price: Decimal
    sale_price: Decimal | None
    current_price: Decimal
    discount_percent: Decimal | None
    badge: Badge | None
    rating: Decimal
    reviews_count: int
    in_stock: bool
    free_shipping: bool
    is_favorite: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class OptionView:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantView:
    id: int
    sku: str
    label: str
    attributes: dict[str, str]
    price: Decimal
    in_stock: bool
    stock: int
    image: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductDetail:
    card: ProductCard
    long_description: str
    images: tuple[str, ...]
    features: tuple[str, ...]
    care_instructions: tuple[str, ...]
    delivery_policy_primary: str
    delivery_policy_secondary: str
    shipping_fee: Decimal | None
    low_stock: bool
    options: tuple[OptionView, ...]
    variants: tuple[VariantView, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchPage:
    ids: tuple[int, ...]
    total: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FacetCount:
    value: str
    label: str
    count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Facets:
    categories: tuple[FacetCount, ...]
    min_price: Decimal | None
    max_price: Decimal | None
    in_stock: int
    out_of_stock: int
    on_sale: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Suggestion:
    id: int
    slug: str
    name: str
    category: str
    image: str
    current_price: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewAuthor:
    id: int
    name: str
    avatar: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewView:
    id: int
    rating: int
    message: str
    verified: bool
    author: ReviewAuthor
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewSummary:
    average: Decimal
    count: int
    distribution: dict[int, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewEligibility:
    can_review: bool
    reason: str | None = None
    existing_review_id: int | None = None


type ProductDocument = dict[str, Any]


@dataclass(frozen=True, slots=True, kw_only=True)
class PricedLine:
    product_id: int
    variant_id: int | None
    sku: str
    name: str
    variant_label: str
    image: str
    unit_price: Decimal
    quantity: int
    free_shipping: bool
    shipping_fee: Decimal | None
    cost_price: Decimal | None = None

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity
