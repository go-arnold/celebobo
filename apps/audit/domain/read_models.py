from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from apps.audit.domain.enums import AuditAction


@dataclass(frozen=True, slots=True, kw_only=True)
class ActorRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeEntry:
    id: int
    timestamp: datetime
    action: AuditAction
    object_type: str
    object_id: str
    object_repr: str
    changes: dict[str, Any]
    actor: ActorRef | None
    remote_addr: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class EventEntry:
    id: UUID
    event_type: str
    name: str
    actor: ActorRef | None
    payload: dict[str, Any]
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackedType:
    key: str
    label: str
