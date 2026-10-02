from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.catalog.domain.read_models import CategoryView, ProductCard
from apps.content.domain.enums import ContactStatus, ContactSubject


@dataclass(frozen=True, slots=True, kw_only=True)
class ContactMessageView:
    id: int
    name: str
    email: str
    phone: str
    subject: ContactSubject
    message: str
    status: ContactStatus
    note: str
    user_id: int | None
    handled_by: str | None
    handled_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriberView:
    id: int
    email: str
    source: str
    is_active: bool
    subscribed_at: datetime
    unsubscribed_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Subscription:
    email: str
    code: str
    discount: int
    already_subscribed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PageView:
    id: int
    slug: str
    title: str
    summary: str
    body: str
    is_published: bool
    position: int
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class FaqView:
    id: int
    question: str
    answer: str
    category: str
    position: int
    is_published: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FaqGroup:
    category: str
    entries: list[FaqView]


@dataclass(frozen=True, slots=True, kw_only=True)
class BannerView:
    id: int
    title: str
    subtitle: str
    image: str
    link_url: str
    link_label: str
    position: int
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingInfo:
    free_threshold: Decimal
    flat_fee: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class SiteSettingsView:
    usd_to_cdf: Decimal
    hotline: str
    whatsapp: str
    whatsapp_url: str
    email: str
    address: str
    opening_hours: list[dict[str, str]]
    payment_methods: list[str]
    social_links: dict[str, str]
    newsletter_discount: int
    shipping: ShippingInfo
    newsletter_code: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryBlock:
    category: CategoryView
    products: list[ProductCard]


@dataclass(frozen=True, slots=True, kw_only=True)
class HomePage:
    banners: list[BannerView]
    deals: list[ProductCard]
    new_arrivals: list[ProductCard]
    best_sellers: list[ProductCard]
    categories: list[CategoryBlock]
