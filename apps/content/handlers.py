from apps.catalog.domain.events import CategoryChanged
from apps.content.domain.events import (
    ContactMessageReceived,
    NewsletterSubscribed,
    SiteContentChanged,
)
from apps.content.facades import ContactFacade, NewsletterFacade
from apps.content.services.cache import ContentCache
from core.container import container
from core.events.bus import event_bus


@event_bus.on(SiteContentChanged, CategoryChanged)
def invalidate_content_cache(_event: SiteContentChanged | CategoryChanged) -> None:
    container.resolve(ContentCache).bump()


@event_bus.on(ContactMessageReceived, background=True)
def acknowledge_contact(event: ContactMessageReceived) -> None:
    container.resolve(ContactFacade).acknowledge(event.message_id)


@event_bus.on(NewsletterSubscribed, background=True)
def welcome_subscriber(event: NewsletterSubscribed) -> None:
    container.resolve(NewsletterFacade).welcome(event.subscriber_id)
