from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus, StockReason
from core.domain.values import UNSET, Maybe


class ProductStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRASH = "trash"
    ALL = "all"


class AdjustmentMode(StrEnum):
    DELTA = "delta"
    SET = "set"


class BulkAction(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    TRASH = "trash"
    RESTORE = "restore"
    SET_CATEGORY = "set_category"
    SET_DISCOUNT = "set_discount"
    CLEAR_DISCOUNT = "clear_discount"


@dataclass(frozen=True, slots=True, kw_only=True)
class OptionInput:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductDraft:
    name: str
    description: str
    category_id: int
    price: Decimal
    sale_price: Decimal | None = None
    cost_price: Decimal | None = None
    long_description: str = ""
    badge: Badge | None = None
    care_instructions: str = ""
    delivery_policy_primary: str = ""
    delivery_policy_secondary: str = ""
    free_shipping: bool = False
    shipping_fee: Decimal | None = None
    stock: int = 0
    stock_threshold: int = 5
    sell_by: date | None = None
    is_active: bool = True
    features: tuple[str, ...] = ()
    options: tuple[OptionInput, ...] = ()
    image_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductChanges:
    name: Maybe[str] = UNSET
    description: Maybe[str] = UNSET
    category_id: Maybe[int] = UNSET
    price: Maybe[Decimal] = UNSET
    sale_price: Maybe[Decimal | None] = UNSET
    cost_price: Maybe[Decimal | None] = UNSET
    long_description: Maybe[str] = UNSET
    badge: Maybe[Badge | None] = UNSET
    care_instructions: Maybe[str] = UNSET
    delivery_policy_primary: Maybe[str] = UNSET
    delivery_policy_secondary: Maybe[str] = UNSET
    free_shipping: Maybe[bool] = UNSET
    shipping_fee: Maybe[Decimal | None] = UNSET
    stock_threshold: Maybe[int] = UNSET
    sell_by: Maybe[date | None] = UNSET
    is_active: Maybe[bool] = UNSET
    features: Maybe[tuple[str, ...]] = UNSET
    options: Maybe[tuple[OptionInput, ...]] = UNSET
    image_ids: Maybe[tuple[int, ...]] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantDraft:
    attributes: Mapping[str, str]
    sku: str | None = None
    price: Decimal | None = None
    stock: int = 0
    image_id: int | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantChanges:
    attributes: Maybe[Mapping[str, str]] = UNSET
    sku: Maybe[str] = UNSET
    price: Maybe[Decimal | None] = UNSET
    image_id: Maybe[int | None] = UNSET
    is_active: Maybe[bool] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class StockAdjustment:
    mode: AdjustmentMode
    value: int
    reason: StockReason
    note: str = ""
    variant_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryDraft:
    name: str
    icon: CategoryIcon = CategoryIcon.MOBILE
    description: str = ""
    image_id: int | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryChanges:
    name: Maybe[str] = UNSET
    icon: Maybe[CategoryIcon] = UNSET
    description: Maybe[str] = UNSET
    image_id: Maybe[int | None] = UNSET
    is_active: Maybe[bool] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class BulkProductAction:
    ids: tuple[int, ...]
    action: BulkAction
    category_id: int | None = None
    percent: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BackofficeProductFilters:
    search: str | None = None
    category_id: int | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    on_sale: bool | None = None
    out_of_stock: bool = False
    low_stock: bool = False
    badge: Badge | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewFilters:
    status: ReviewStatus | None = None
    product_id: int | None = None
    rating: int | None = None
    search: str | None = None
