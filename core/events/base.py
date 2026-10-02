from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast, dataclass_transform
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_now)
    actor_id: int | None = None

    @classmethod
    def event_name(cls) -> str:
        return f"{cls.__module__}.{cls.__qualname__}"


@dataclass_transform(frozen_default=True, kw_only_default=True, field_specifiers=(field,))
def domain_event[E: type[DomainEvent]](cls: E) -> E:
    return cast(E, dataclass(frozen=True, slots=True, kw_only=True)(cls))
