from core.events.base import DomainEvent, domain_event


@domain_event
class LoyaltySettingsChanged(DomainEvent):
    pass
