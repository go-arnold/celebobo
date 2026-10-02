from django.utils import timezone

from apps.audit.adapters.gateways import AccountActorNames
from apps.audit.conf import audit_settings
from apps.audit.facades import AuditFacade
from apps.audit.repositories import ChangeRepository, EventRepository
from apps.audit.selectors import ChangeSelector, EventSelector
from apps.audit.services.contracts import ActorNames
from apps.audit.services.recorder import EventRecorder
from apps.audit.services.retention import RetentionService
from core.container import Container, Lifetime


def register(container: Container) -> None:
    container.register(ActorNames, lambda _: AccountActorNames())
    container.register(AuditFacade, _audit_facade, lifetime=Lifetime.TRANSIENT)


def _audit_facade(container: Container) -> AuditFacade:
    settings = audit_settings()
    names = container.resolve(ActorNames)
    events = EventRepository()
    return AuditFacade(
        changes=ChangeSelector(),
        events=EventSelector(),
        names=names,
        recorder=EventRecorder(events, ignored=frozenset(settings.ignored_events)),
        retention=RetentionService(
            events,
            ChangeRepository(),
            retention_days=settings.retention_days,
            clock=timezone.now,
        ),
    )
