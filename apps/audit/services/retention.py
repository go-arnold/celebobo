from collections.abc import Callable
from datetime import datetime, timedelta

from apps.audit.repositories import ChangeRepository, EventRepository


class RetentionService:
    def __init__(
        self,
        events: EventRepository,
        changes: ChangeRepository,
        *,
        retention_days: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._events = events
        self._changes = changes
        self._retention_days = retention_days
        self._clock = clock

    def purge(self) -> dict[str, int]:
        before = self._clock() - timedelta(days=self._retention_days)
        return {"changes": self._changes.purge(before), "events": self._events.purge(before)}
