from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.content.domain.enums import ContactStatus, ContactSubject
from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class SendContactMessage:
    name: str
    email: str
    subject: ContactSubject
    message: str
    phone: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class HandleContactMessage:
    status: Maybe[ContactStatus] = UNSET
    note: Maybe[str] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class ContactFilters:
    status: ContactStatus | None = None
    subject: ContactSubject | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PageFields:
    slug: str
    title: str
    body: str
    summary: str = ""
    is_published: bool = True
    position: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class PageChanges:
    slug: Maybe[str] = UNSET
    title: Maybe[str] = UNSET
    body: Maybe[str] = UNSET
    summary: Maybe[str] = UNSET
    is_published: Maybe[bool] = UNSET
    position: Maybe[int] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class FaqFields:
    question: str
    answer: str
    category: str = ""
    position: int = 0
    is_published: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class FaqChanges:
    question: Maybe[str] = UNSET
    answer: Maybe[str] = UNSET
    category: Maybe[str] = UNSET
    position: Maybe[int] = UNSET
    is_published: Maybe[bool] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class BannerFields:
    title: str
    image: str
    subtitle: str = ""
    link_url: str = ""
    link_label: str = ""
    position: int = 0
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BannerChanges:
    title: Maybe[str] = UNSET
    image: Maybe[str] = UNSET
    subtitle: Maybe[str] = UNSET
    link_url: Maybe[str] = UNSET
    link_label: Maybe[str] = UNSET
    position: Maybe[int] = UNSET
    is_active: Maybe[bool] = UNSET
    starts_at: Maybe[datetime | None] = UNSET
    ends_at: Maybe[datetime | None] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingsChanges:
    usd_to_cdf: Maybe[Decimal] = UNSET
    hotline: Maybe[str] = UNSET
    whatsapp: Maybe[str] = UNSET
    email: Maybe[str] = UNSET
    address: Maybe[str] = UNSET
    opening_hours: Maybe[list[dict[str, str]]] = UNSET
    payment_methods: Maybe[list[str]] = UNSET
    social_links: Maybe[dict[str, str]] = UNSET
    newsletter_code: Maybe[str] = UNSET
    newsletter_discount: Maybe[int] = UNSET
