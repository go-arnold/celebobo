from time import time

from django.utils import timezone

from apps.content.adapters.gateways import CatalogShowcase, OrdersShipping
from apps.content.adapters.media_references import ContentMediaReferences
from apps.content.adapters.storefront import HttpRevalidator
from apps.content.conf import storefront_settings
from apps.content.domain.errors import (
    BannerNotFound,
    FaqEntryNotFound,
    PageNotFound,
    SectionNotFound,
)
from apps.content.facades import (
    ContactFacade,
    NewsletterFacade,
    SiteContentFacade,
    StorefrontFacade,
)
from apps.content.models import ContactMessage, FaqEntry, Page
from apps.content.repositories import (
    BannerRepository,
    ModelRepository,
    SectionRepository,
    SettingsRepository,
    SubscriberRepository,
)
from apps.content.selectors import (
    BannerSelector,
    ContactSelector,
    FaqSelector,
    PageSelector,
    SectionSelector,
    SubscriberSelector,
)
from apps.content.services.cache import ContentCache
from apps.content.services.contact import ContactService
from apps.content.services.contracts import PageRevalidator, ShippingSource, Showcase
from apps.content.services.editors import Editor
from apps.content.services.home import HomeService, flatten
from apps.content.services.mailer import ContentMailer
from apps.content.services.newsletter import NewsletterService
from apps.content.services.rules import BannerRules, SectionRules, UniqueSlug
from apps.content.services.site import SiteSettingsService
from apps.content.services.storefront import PendingTags
from apps.content.tasks import revalidate_storefront
from apps.media.services.references import media_references
from core.container import Container, Lifetime
from core.domain.actor import Actor
from core.events.contracts import EventPublisher

HOME_SECTION_SIZE = 8
HOME_CATEGORY_BLOCKS = 4


def register(container: Container) -> None:
    media_references.add("content", ContentMediaReferences, replace=True)
    container.register(ContentCache, lambda _: ContentCache())
    container.register(Showcase, lambda _: CatalogShowcase())
    container.register(ShippingSource, lambda _: OrdersShipping())
    container.register(ContactFacade, _contact_facade, lifetime=Lifetime.TRANSIENT)
    container.register(NewsletterFacade, _newsletter_facade, lifetime=Lifetime.TRANSIENT)
    container.register(SiteContentFacade, _content_facade, lifetime=Lifetime.TRANSIENT)
    container.register(StorefrontFacade, _storefront_facade, lifetime=Lifetime.TRANSIENT)


def _contact_facade(container: Container) -> ContactFacade:
    return ContactFacade(
        contact=ContactService(ModelRepository(ContactMessage), clock=timezone.now),
        selector=ContactSelector(),
        site=SiteSettingsService(SettingsRepository()),
        mailer=ContentMailer(),
        publisher=container.resolve(EventPublisher),
    )


def _newsletter_facade(container: Container) -> NewsletterFacade:
    return NewsletterFacade(
        newsletter=NewsletterService(SubscriberRepository(), clock=timezone.now),
        selector=SubscriberSelector(),
        site=SiteSettingsService(SettingsRepository()),
        mailer=ContentMailer(),
        publisher=container.resolve(EventPublisher),
    )


def _content_facade(container: Container) -> SiteContentFacade:
    pages = ModelRepository(Page)
    banners = BannerSelector(timezone.now)
    banner_repository = BannerRepository()
    sections = SectionSelector()
    section_repository = SectionRepository()
    showcase = container.resolve(Showcase)

    def visible(product_id: int) -> bool:
        return bool(showcase.cards(Actor.anonymous(), [product_id]))

    def visible_category(category_id: int) -> bool:
        return any(category.id == category_id for category in flatten(showcase.categories()))

    return SiteContentFacade(
        pages=Editor(pages, not_found=PageNotFound, validate=UniqueSlug(pages)),
        faq=Editor(ModelRepository(FaqEntry), not_found=FaqEntryNotFound),
        banners=Editor(banner_repository, not_found=BannerNotFound, validate=BannerRules(visible)),
        banner_repository=banner_repository,
        sections=Editor(
            section_repository,
            not_found=SectionNotFound,
            validate=SectionRules(visible_category),
        ),
        section_repository=section_repository,
        section_selector=sections,
        page_selector=PageSelector(),
        faq_selector=FaqSelector(),
        banner_selector=banners,
        site=SiteSettingsService(SettingsRepository()),
        shipping=container.resolve(ShippingSource),
        home=HomeService(
            container.resolve(Showcase),
            banners,
            sections,
            section_size=HOME_SECTION_SIZE,
            category_blocks=HOME_CATEGORY_BLOCKS,
        ),
        showcase=container.resolve(Showcase),
        cache=container.resolve(ContentCache),
        publisher=container.resolve(EventPublisher),
    )


def _storefront_facade(container: Container) -> StorefrontFacade:
    settings = storefront_settings()
    revalidator: PageRevalidator | None = (
        HttpRevalidator(
            settings.revalidate_url,
            settings.revalidate_secret,
            timeout=settings.revalidate_timeout,
        )
        if settings.revalidate_url
        else None
    )
    return StorefrontFacade(
        catalog=container.resolve(Showcase),
        pending=PendingTags(clock=time, debounce=settings.debounce, max_wait=settings.max_wait),
        revalidator=revalidator,
        schedule=lambda delay: revalidate_storefront.apply_async(countdown=delay),
        debounce=settings.debounce,
    )
