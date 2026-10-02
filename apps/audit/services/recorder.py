from apps.audit.repositories import EventRepository
from core.events.base import DomainEvent
from core.events.codec import encode

BASE_FIELDS = frozenset({"event_id", "occurred_at", "actor_id"})


class EventRecorder:
    def __init__(self, events: EventRepository, *, ignored: frozenset[str]) -> None:
        self._events = events
        self._ignored = ignored

    def record(self, event: DomainEvent) -> bool:
        event_type = event.event_name()
        if event_type in self._ignored:
            return False
        payload = {key: value for key, value in encode(event).items() if key not in BASE_FIELDS}
        return self._events.record(
            event_id=event.event_id,
            event_type=event_type,
            actor_id=event.actor_id,
            payload=payload,
            occurred_at=event.occurred_at,
        )
