from datetime import datetime

from core.events.base import DomainEvent, domain_event


@domain_event
class LoyaltySettingsChanged(DomainEvent):
    pass


@domain_event
class MembershipRequested(DomainEvent):
    request_id: int
    user_id: int
    client_name: str
    plan: str


@domain_event
class MembershipStarted(DomainEvent):
    user_id: int
    plan: str
    ends_at: datetime


@domain_event
class MembershipRequestRejected(DomainEvent):
    user_id: int
    request_id: int
    note: str


@domain_event
class MembershipEnding(DomainEvent):
    user_id: int
    ends_at: datetime
