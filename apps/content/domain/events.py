from core.events.base import DomainEvent, domain_event


@domain_event
class ContactMessageReceived(DomainEvent):
    message_id: int


@domain_event
class NewsletterSubscribed(DomainEvent):
    subscriber_id: int


# through the link of a newsletter e-mail
@domain_event
class NewsletterUnsubscribed(DomainEvent):
    subscriber_id: int


@domain_event
class SiteContentChanged(DomainEvent):
    section: str
