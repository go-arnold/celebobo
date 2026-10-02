from dataclasses import dataclass, field

from core.events.base import DomainEvent
from core.observability.metrics import Tags


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)

    def of_type[E: DomainEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]

    def single[E: DomainEvent](self, event_type: type[E]) -> E:
        matches = self.of_type(event_type)
        if len(matches) != 1:
            raise AssertionError(f"Expected one {event_type.__name__}, got {len(matches)}")
        return matches[0]


@dataclass(frozen=True, slots=True)
class MetricRecord:
    kind: str
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)


class InMemoryMetrics:
    def __init__(self) -> None:
        self.records: list[MetricRecord] = []

    def increment(self, name: str, *, value: int = 1, tags: Tags | None = None) -> None:
        self.records.append(MetricRecord("counter", name, value, dict(tags or {})))

    def timing(self, name: str, milliseconds: float, *, tags: Tags | None = None) -> None:
        self.records.append(MetricRecord("timing", name, milliseconds, dict(tags or {})))

    def gauge(self, name: str, value: float, *, tags: Tags | None = None) -> None:
        self.records.append(MetricRecord("gauge", name, value, dict(tags or {})))

    def named(self, name: str) -> list[MetricRecord]:
        return [record for record in self.records if record.name == name]
