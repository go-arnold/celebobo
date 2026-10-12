from apps.catalog.domain.events import (
    CategoryChanged,
    ProductChanged,
    ProductRemoved,
    ProductsChanged,
    ProductsRemoved,
)
from apps.content.domain.events import (
    ContactMessageReceived,
    NewsletterSubscribed,
    SiteContentChanged,
)
from apps.content.facades import ContactFacade, NewsletterFacade, StorefrontFacade
from apps.content.services.cache import ContentCache
from core.container import container
from core.events.bus import event_bus


@event_bus.on(SiteContentChanged, CategoryChanged)
def invalidate_content_cache(_event: SiteContentChanged | CategoryChanged) -> None:
    container.resolve(ContentCache).bump()


@event_bus.on(ProductChanged, ProductsChanged, ProductRemoved, ProductsRemoved)
def revalidate_product_pages(
    event: ProductChanged | ProductsChanged | ProductRemoved | ProductsRemoved,
) -> None:
    container.resolve(StorefrontFacade).products_changed(event.product_ids)


@event_bus.on(CategoryChanged)
def revalidate_category_pages(event: CategoryChanged) -> None:
    container.resolve(StorefrontFacade).category_changed(event.category_id)


@event_bus.on(SiteContentChanged)
def revalidate_site_pages(event: SiteContentChanged) -> None:
    container.resolve(StorefrontFacade).section_changed(event.section)


@event_bus.on(ContactMessageReceived, background=True)
def acknowledge_contact(event: ContactMessageReceived) -> None:
    container.resolve(ContactFacade).acknowledge(event.message_id)


@event_bus.on(NewsletterSubscribed, background=True)
def welcome_subscriber(event: NewsletterSubscribed) -> None:
    container.resolve(NewsletterFacade).welcome(event.subscriber_id)
