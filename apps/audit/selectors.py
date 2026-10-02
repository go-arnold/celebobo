from datetime import date, datetime, time
from typing import Any

from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.domain.enums import AuditAction
from apps.audit.domain.errors import AuditEntryNotFound
from apps.audit.domain.queries import ChangeFilters, EventFilters
from apps.audit.domain.read_models import ActorRef, ChangeEntry, EventEntry, TrackedType
from apps.audit.models import EventRecord


class ChangeSelector:
    def page(
        self, filters: ChangeFilters, *, offset: int, limit: int
    ) -> tuple[list[ChangeEntry], int]:
        entries = _changes(filters)
        page = list(
            entries.select_related("content_type").order_by("-timestamp", "-pk")[
                offset : offset + limit
            ]
        )
        return [_change(entry) for entry in page], entries.count()

    def one(self, entry_id: int) -> ChangeEntry:
        entry = LogEntry.objects.select_related("content_type").filter(pk=entry_id).first()
        if entry is None:
            raise AuditEntryNotFound
        return _change(entry)

    def tracked_types(self) -> list[TrackedType]:
        models = sorted(auditlog.get_models(), key=lambda model: model._meta.label_lower)
        return [
            TrackedType(key=model._meta.label_lower, label=str(model._meta.verbose_name))
            for model in models
        ]


class EventSelector:
    def page(
        self, filters: EventFilters, *, offset: int, limit: int
    ) -> tuple[list[EventEntry], int]:
        records = _events(filters)
        page = list(records.order_by("-occurred_at")[offset : offset + limit])
        return [_event(record) for record in page], records.count()

    def event_types(self) -> list[str]:
        return list(
            EventRecord.objects.order_by("event_type")
            .values_list("event_type", flat=True)
            .distinct()
        )


def _changes(filters: ChangeFilters) -> QuerySet[LogEntry]:
    entries: QuerySet[Any] = LogEntry.objects.all()
    if filters.actor_id is not None:
        entries = entries.filter(actor_id=filters.actor_id)
    if filters.action is not None:
        entries = entries.filter(action=filters.action.code)
    if filters.object_type:
        app_label, _, model = filters.object_type.partition(".")
        entries = entries.filter(content_type__app_label=app_label, content_type__model=model)
    if filters.object_id:
        entries = entries.filter(object_pk=filters.object_id)
    entries = _dated(entries, "timestamp", filters.date_from, filters.date_to)
    if filters.search:
        term = filters.search.strip()
        entries = entries.filter(Q(object_repr__icontains=term) | Q(actor_email__icontains=term))
    return entries


def _events(filters: EventFilters) -> QuerySet[EventRecord]:
    records = EventRecord.objects.all()
    if filters.event_type:
        records = records.filter(event_type__iendswith=filters.event_type)
    if filters.actor_id is not None:
        records = records.filter(actor_id=filters.actor_id)
    return _dated(records, "occurred_at", filters.date_from, filters.date_to)


def _dated[Q_: QuerySet[Any]](
    queryset: Q_, field: str, date_from: date | None, date_to: date | None
) -> Q_:
    if date_from is not None:
        queryset = queryset.filter(**{f"{field}__gte": _start(date_from)})
    if date_to is not None:
        queryset = queryset.filter(**{f"{field}__lte": _end(date_to)})
    return queryset


def _change(entry: LogEntry) -> ChangeEntry:
    return ChangeEntry(
        id=entry.pk,
        timestamp=entry.timestamp,
        action=AuditAction.from_code(entry.action),
        object_type=f"{entry.content_type.app_label}.{entry.content_type.model}",
        object_id=str(entry.object_pk),
        object_repr=entry.object_repr,
        changes=dict(entry.changes or {}),
        actor=_actor(entry.actor_id, entry.actor_email or ""),
        remote_addr=entry.remote_addr,
    )


def _event(record: EventRecord) -> EventEntry:
    return EventEntry(
        id=record.event_id,
        event_type=record.event_type,
        name=record.event_type.rsplit(".", 1)[-1],
        actor=_actor(record.actor_id, ""),
        payload=dict(record.payload),
        occurred_at=record.occurred_at,
    )


def _actor(actor_id: int | None, name: str) -> ActorRef | None:
    return ActorRef(id=actor_id, name=name) if actor_id is not None else None


def _start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _end(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max))
