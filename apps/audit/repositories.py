from datetime import datetime
from typing import Any
from uuid import UUID

from auditlog.models import LogEntry

from apps.audit.models import EventRecord


class EventRepository:
    def record(
        self,
        *,
        event_id: UUID,
        event_type: str,
        actor_id: int | None,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> bool:
        _, created = EventRecord.objects.get_or_create(
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "actor_id": actor_id,
                "payload": payload,
                "occurred_at": occurred_at,
            },
        )
        return created

    def purge(self, before: datetime) -> int:
        deleted, _ = EventRecord.objects.filter(occurred_at__lt=before).delete()
        return deleted


class ChangeRepository:
    def purge(self, before: datetime) -> int:
        deleted: int = LogEntry.objects.filter(timestamp__lt=before).delete()[0]
        return deleted
