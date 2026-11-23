from core.events.base import DomainEvent, domain_event


@domain_event
class LevelChanged(DomainEvent):
    reseller_id: int
    previous: str
    level: str
    level_label: str = ""


# notified (may explain), applied, dropped: the reseller is told each time
@domain_event
class SanctionUpdated(DomainEvent):
    sanction_id: int
    reseller_id: int
    kind: str
    status: str
    message: str = ""
