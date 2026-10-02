from core.events.base import DomainEvent, domain_event


@domain_event
class ContactMessageReceived(DomainEvent):
    message_id: int


@domain_event
class NewsletterSubscribed(DomainEvent):
    subscriber_id: int


@domain_event
class SiteContentChanged(DomainEvent):
    section: str
