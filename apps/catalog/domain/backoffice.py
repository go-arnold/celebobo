from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus, StockReason
from apps.catalog.domain.management import ProductStatus
from apps.catalog.domain.read_models import CategoryRef, OptionView, ReviewAuthor


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminProductRow:
    id: int
    slug: str
    name: str
    category: CategoryRef
    image: str
    price: Decimal
    sale_price: Decimal | None
    cost_price: Decimal | None
    current_price: Decimal
    margin: Decimal | None
    margin_percent: Decimal | None
    stock: int
    stock_threshold: int
    low_stock: bool
    status: ProductStatus
    badge: Badge | None
    variants_count: int
    sales_count: int
    rating: Decimal
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminImage:
    url: str
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminVariant:
    id: int
    sku: str
    label: str
    attributes: dict[str, str]
    price: Decimal | None
    stock: int
    image: str
    is_active: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminProductDetail:
    row: AdminProductRow
    description: str
    long_description: str
    care_instructions: str
    delivery_policy_primary: str
    delivery_policy_secondary: str
    free_shipping: bool
    shipping_fee: Decimal | None
    sell_by: date | None
    features: tuple[str, ...]
    options: tuple[OptionView, ...]
    images: tuple[AdminImage, ...]
    variants: tuple[AdminVariant, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductStats:
    total: int
    active: int
    on_sale: int
    out_of_stock: int
    low_stock: int
    stock_value: Decimal
    trashed: int


@dataclass(frozen=True, slots=True, kw_only=True)
class StockMovementView:
    id: int
    product_id: int
    variant_id: int | None
    delta: int
    balance_after: int
    reason: StockReason
    note: str
    actor_name: str | None
    source_type: str
    source_id: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class LowStockItem:
    product_id: int
    variant_id: int | None
    name: str
    variant_label: str
    stock: int
    threshold: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminCategory:
    id: int
    slug: str
    name: str
    description: str
    image: str
    icon: CategoryIcon
    is_active: bool
    position: int
    products_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductRef:
    id: int
    slug: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminReview:
    id: int
    product: ProductRef
    author: ReviewAuthor
    rating: int
    message: str
    status: ReviewStatus
    verified: bool
    created_at: datetime
