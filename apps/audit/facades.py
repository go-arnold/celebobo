from dataclasses import replace

from django.db import transaction

from apps.audit.domain.queries import ChangeFilters, EventFilters
from apps.audit.domain.read_models import ActorRef, ChangeEntry, EventEntry, TrackedType
from apps.audit.selectors import ChangeSelector, EventSelector
from apps.audit.services.contracts import ActorNames
from apps.audit.services.recorder import EventRecorder
from apps.audit.services.retention import RetentionService
from core.events.base import DomainEvent
from core.observability.decorators import logged_facade


@logged_facade
class AuditFacade:
    def __init__(
        self,
        *,
        changes: ChangeSelector,
        events: EventSelector,
        recorder: EventRecorder,
        retention: RetentionService,
        names: ActorNames,
    ) -> None:
        self._names = names
        self._changes = changes
        self._events = events
        self._recorder = recorder
        self._retention = retention

    def changes(
        self, filters: ChangeFilters, *, offset: int, limit: int
    ) -> tuple[list[ChangeEntry], int]:
        entries, total = self._changes.page(filters, offset=offset, limit=limit)
        return self._named(entries), total

    def change(self, entry_id: int) -> ChangeEntry:
        return self._named([self._changes.one(entry_id)])[0]

    def tracked_types(self) -> list[TrackedType]:
        return self._changes.tracked_types()

    def events(
        self, filters: EventFilters, *, offset: int, limit: int
    ) -> tuple[list[EventEntry], int]:
        entries, total = self._events.page(filters, offset=offset, limit=limit)
        return self._named(entries), total

    def event_types(self) -> list[str]:
        return self._events.event_types()

    def record(self, event: DomainEvent) -> bool:
        return self._recorder.record(event)

    def purge(self) -> dict[str, int]:
        with transaction.atomic():
            return self._retention.purge()

    def _named[E: (ChangeEntry, EventEntry)](self, entries: list[E]) -> list[E]:
        names = self._names.names([entry.actor.id for entry in entries if entry.actor])
        return [
            replace(entry, actor=_named_actor(entry.actor, names)) if entry.actor else entry
            for entry in entries
        ]


def _named_actor(actor: ActorRef, names: dict[int, str]) -> ActorRef:
    return ActorRef(id=actor.id, name=names.get(actor.id) or actor.name)
