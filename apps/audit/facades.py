from dataclasses import replace

import structlog
from django.db import transaction

from apps.audit.domain.events import RetentionApplied
from apps.audit.domain.queries import ChangeFilters, EventFilters
from apps.audit.domain.read_models import ActorRef, ChangeEntry, EventEntry, TrackedType
from apps.audit.domain.retention import RetentionReport
from apps.audit.selectors import ChangeSelector, EventSelector
from apps.audit.services.contracts import ActorNames
from apps.audit.services.recorder import EventRecorder
from apps.audit.services.retention import RetentionRunner, RetentionService
from core.events.base import DomainEvent
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade

logger = structlog.get_logger(__name__)


@logged_facade
class AuditFacade:
    def __init__(
        self,
        *,
        changes: ChangeSelector,
        events: EventSelector,
        recorder: EventRecorder,
        retention: RetentionService,
        runner: RetentionRunner,
        names: ActorNames,
        publisher: EventPublisher,
    ) -> None:
        self._names = names
        self._changes = changes
        self._events = events
        self._recorder = recorder
        self._retention = retention
        self._runner = runner
        self._publisher = publisher

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

    def retention_rules(self) -> list[str]:
        return self._runner.names()

    # each rule commits batch by batch; a real run leaves one entry in the audit trail
    def apply_retention(self, rule: str, *, dry_run: bool = False) -> RetentionReport:
        report = self._runner.run(rule, dry_run=dry_run)
        logger.info(
            "retention.applied", rule=rule, affected=report.affected, dry_run=report.dry_run
        )
        if not dry_run:
            self._publisher.publish(
                RetentionApplied(rule=rule, affected=report.affected, actor_id=None)
            )
        return report

    def _named[E: (ChangeEntry, EventEntry)](self, entries: list[E]) -> list[E]:
        names = self._names.names([entry.actor.id for entry in entries if entry.actor])
        return [
            replace(entry, actor=_named_actor(entry.actor, names)) if entry.actor else entry
            for entry in entries
        ]


def _named_actor(actor: ActorRef, names: dict[int, str]) -> ActorRef:
    return ActorRef(id=actor.id, name=names.get(actor.id) or actor.name)
