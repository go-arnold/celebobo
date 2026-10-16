from core.events.base import DomainEvent, domain_event


@domain_event
class LoyaltySettingsChanged(DomainEvent):
    pass


@domain_event
class PointsAwarded(DomainEvent):
    user_id: int
    points: int
    reason: str
    rule_id: int | None = None


@domain_event
class LoyaltyRuleChanged(DomainEvent):
    rule_id: int
    action: str  # created | updated | deleted
