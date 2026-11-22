from core.events.base import DomainEvent, domain_event


# one entry per real (not dry) run of a retention rule, written to the audit trail
@domain_event
class RetentionApplied(DomainEvent):
    rule: str
    affected: int
