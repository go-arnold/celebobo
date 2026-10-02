from core.events.base import DomainEvent, domain_event


@domain_event
class ApplicationSubmitted(DomainEvent):
    application_id: int


@domain_event
class ApplicationApproved(DomainEvent):
    application_id: int
    reseller_id: int
    account_created: bool


@domain_event
class ApplicationRejected(DomainEvent):
    application_id: int
