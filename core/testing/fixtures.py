from collections.abc import Callable, Iterator

import pytest

from core.container import container
from core.domain.actor import Actor, Role
from core.events.contracts import EventPublisher
from core.observability.metrics import Metrics
from core.testing.fakes import InMemoryMetrics, RecordingPublisher


@pytest.fixture
def published_events() -> Iterator[RecordingPublisher]:
    publisher = RecordingPublisher()
    with container.override(EventPublisher, publisher):
        yield publisher


@pytest.fixture
def recorded_metrics() -> Iterator[InMemoryMetrics]:
    metrics = InMemoryMetrics()
    with container.override(Metrics, metrics):
        yield metrics


@pytest.fixture
def make_actor() -> Callable[..., Actor]:
    def build(role: Role = Role.CLIENT, user_id: int | None = 1) -> Actor:
        return Actor(role=role, user_id=None if role is Role.ANONYMOUS else user_id)

    return build
