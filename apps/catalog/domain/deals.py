from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from apps.catalog.domain.read_models import ProductCard, ProductDetail
from apps.catalog.domain.rules import discount_percent
from core.domain.values import UNSET, Maybe


class DealStatus(StrEnum):
    LIVE = "live"
    SCHEDULED = "scheduled"
    ENDED = "ended"


@dataclass(frozen=True, slots=True, kw_only=True)
class DealTerms:
    id: int
    product_id: int
    variant_id: int | None
    deal_price: Decimal
    regular_price: Decimal
    starts_at: datetime
    ends_at: datetime
    quantity: int | None
    gift_label: str
    is_active: bool
    sold: int = 0

    @property
    def remaining(self) -> int | None:
        return None if self.quantity is None else max(self.quantity - self.sold, 0)

    def status(self, now: datetime) -> DealStatus:
        if not self.is_active or now >= self.ends_at or self.remaining == 0:
            return DealStatus.ENDED
        if now < self.starts_at:
            return DealStatus.SCHEDULED
        return DealStatus.LIVE

    # a line larger than the units left pays the regular price rather than being split
    def covers(self, variant_id: int | None, quantity: int) -> bool:
        return self.variant_id == variant_id and (
            self.remaining is None or quantity <= self.remaining
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DealDraft:
    product_id: int
    deal_price: Decimal
    starts_at: datetime
    ends_at: datetime
    variant_id: int | None = None
    quantity: int | None = None
    gift_label: str = ""
    is_active: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class DealChanges:
    variant_id: Maybe[int | None] = UNSET
    deal_price: Maybe[Decimal] = UNSET
    starts_at: Maybe[datetime] = UNSET
    ends_at: Maybe[datetime] = UNSET
    quantity: Maybe[int | None] = UNSET
    gift_label: Maybe[str] = UNSET
    is_active: Maybe[bool] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class DealProduct:
    id: int
    slug: str
    name: str
    image: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminDeal:
    terms: DealTerms
    product: DealProduct
    variant_label: str
    status: DealStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class DealOfTheDay:
    terms: DealTerms
    product: ProductDetail

    @property
    def sold(self) -> int | None:
        return None if self.terms.quantity is None else self.terms.sold


def card_on_deal(card: ProductCard, deal: DealTerms | None) -> ProductCard:
    if deal is None:
        return card
    return replace(
        card,
        price=deal.regular_price,
        sale_price=deal.deal_price,
        current_price=deal.deal_price,
        discount_percent=discount_percent(deal.regular_price, deal.deal_price),
    )


def detail_on_deal(detail: ProductDetail, deal: DealTerms | None) -> ProductDetail:
    if deal is None:
        return detail
    return replace(
        detail,
        card=card_on_deal(detail.card, deal),
        variants=tuple(
            replace(variant, price=deal.deal_price) if variant.id == deal.variant_id else variant
            for variant in detail.variants
        ),
    )
