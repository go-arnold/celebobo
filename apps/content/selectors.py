import re
from collections.abc import Callable, Iterator
from datetime import datetime

from django.db.models import Count, Q, QuerySet

from apps.content.domain.commands import ContactFilters
from apps.content.domain.enums import ContactStatus, ContactSubject
from apps.content.domain.errors import ContactMessageNotFound, PageNotFound
from apps.content.domain.read_models import (
    BannerView,
    ContactMessageView,
    FaqGroup,
    FaqView,
    PageView,
    ShippingInfo,
    SiteSettingsView,
    SubscriberView,
)
from apps.content.models import Banner, ContactMessage, FaqEntry, Page, SiteSettings, Subscriber

DIGITS = re.compile(r"\D")


class ContactSelector:
    def page(
        self, filters: ContactFilters, *, offset: int, limit: int
    ) -> tuple[list[ContactMessageView], int, dict[str, int]]:
        messages = ContactMessage.objects.select_related("handled_by")
        if filters.status is not None:
            messages = messages.filter(status=filters.status.value)
        if filters.subject is not None:
            messages = messages.filter(subject=filters.subject.value)
        if filters.search:
            term = filters.search.strip()
            messages = messages.filter(
                Q(name__icontains=term) | Q(email__icontains=term) | Q(message__icontains=term)
            )
        page = messages[offset : offset + limit]
        return [to_contact_view(message) for message in page], messages.count(), self.counts()

    def one(self, message_id: int) -> ContactMessageView:
        message = ContactMessage.objects.select_related("handled_by").filter(pk=message_id).first()
        if message is None:
            raise ContactMessageNotFound
        return to_contact_view(message)

    def counts(self) -> dict[str, int]:
        totals = ContactMessage.objects.aggregate(
            **{item.value: Count("pk", filter=Q(status=item.value)) for item in ContactStatus}
        )
        return {name: int(value) for name, value in totals.items()}


class SubscriberSelector:
    def page(
        self, *, active: bool | None, search: str | None, offset: int, limit: int
    ) -> tuple[list[SubscriberView], int]:
        subscribers = self._filtered(active, search)
        page = subscribers[offset : offset + limit]
        return [to_subscriber_view(item) for item in page], subscribers.count()

    def export(self, *, active: bool | None) -> Iterator[SubscriberView]:
        for subscriber in self._filtered(active, None).iterator(chunk_size=500):
            yield to_subscriber_view(subscriber)

    @staticmethod
    def _filtered(active: bool | None, search: str | None) -> QuerySet[Subscriber]:
        subscribers = Subscriber.objects.all()
        if active is not None:
            subscribers = subscribers.filter(unsubscribed_at__isnull=active)
        if search:
            subscribers = subscribers.filter(email__icontains=search.strip())
        return subscribers


class PageSelector:
    def published(self, slug: str) -> PageView:
        page = Page.objects.filter(slug=slug, is_published=True).first()
        if page is None:
            raise PageNotFound
        return to_page_view(page)

    def listing(self, *, published_only: bool) -> list[PageView]:
        pages = Page.objects.filter(is_published=True) if published_only else Page.objects.all()
        return [to_page_view(page) for page in pages]


class FaqSelector:
    def groups(self) -> list[FaqGroup]:
        groups: dict[str, list[FaqView]] = {}
        for entry in FaqEntry.objects.filter(is_published=True):
            groups.setdefault(entry.category, []).append(to_faq_view(entry))
        return [
            FaqGroup(category=category, entries=entries) for category, entries in groups.items()
        ]

    def all(self) -> list[FaqView]:
        return [to_faq_view(entry) for entry in FaqEntry.objects.all()]


class BannerSelector:
    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def live(self) -> list[BannerView]:
        now = self._clock()
        banners = Banner.objects.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        )
        return [to_banner_view(banner) for banner in banners]

    def all(self) -> list[BannerView]:
        return [to_banner_view(banner) for banner in Banner.objects.all()]


def to_settings_view(
    settings: SiteSettings, shipping: ShippingInfo, *, include_private: bool = False
) -> SiteSettingsView:
    digits = DIGITS.sub("", settings.whatsapp)
    return SiteSettingsView(
        usd_to_cdf=settings.usd_to_cdf,
        hotline=settings.hotline,
        whatsapp=settings.whatsapp,
        whatsapp_url=f"https://wa.me/{digits}" if digits else "",
        email=settings.email,
        address=settings.address,
        opening_hours=list(settings.opening_hours),
        payment_methods=list(settings.payment_methods),
        social_links=dict(settings.social_links),
        newsletter_discount=settings.newsletter_discount,
        shipping=shipping,
        newsletter_code=settings.newsletter_code if include_private else "",
    )


def to_contact_view(message: ContactMessage) -> ContactMessageView:
    handler = message.handled_by
    return ContactMessageView(
        id=message.pk,
        name=message.name,
        email=message.email,
        phone=message.phone,
        subject=ContactSubject(message.subject),
        message=message.message,
        status=ContactStatus(message.status),
        note=message.note,
        user_id=message.user_id,
        handled_by=(handler.get_full_name() or handler.email) if handler else None,
        handled_at=message.handled_at,
        created_at=message.created_at,
    )


def to_subscriber_view(subscriber: Subscriber) -> SubscriberView:
    return SubscriberView(
        id=subscriber.pk,
        email=subscriber.email,
        source=subscriber.source,
        is_active=subscriber.is_active,
        subscribed_at=subscriber.subscribed_at,
        unsubscribed_at=subscriber.unsubscribed_at,
    )


def to_page_view(page: Page) -> PageView:
    return PageView(
        id=page.pk,
        slug=page.slug,
        title=page.title,
        summary=page.summary,
        body=page.body,
        is_published=page.is_published,
        position=page.position,
        updated_at=page.updated_at,
    )


def to_faq_view(entry: FaqEntry) -> FaqView:
    return FaqView(
        id=entry.pk,
        question=entry.question,
        answer=entry.answer,
        category=entry.category,
        position=entry.position,
        is_published=entry.is_published,
    )


def to_banner_view(banner: Banner) -> BannerView:
    return BannerView(
        id=banner.pk,
        title=banner.title,
        subtitle=banner.subtitle,
        image=banner.image,
        link_url=banner.link_url,
        link_label=banner.link_label,
        position=banner.position,
        is_active=banner.is_active,
        starts_at=banner.starts_at,
        ends_at=banner.ends_at,
    )
