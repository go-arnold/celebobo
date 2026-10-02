from apps.audit.facades import AuditFacade
from core.container import container
from core.events.base import DomainEvent
from core.events.bus import event_bus


@event_bus.on(DomainEvent, background=True)
def record_domain_event(event: DomainEvent) -> None:
    container.resolve(AuditFacade).record(event)
