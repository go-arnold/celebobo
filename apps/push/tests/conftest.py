from collections.abc import Iterator

import pytest

from apps.orders.tests.conftest import api, as_user
from apps.push.domain.messages import DeliveryOutcome, Endpoint, PushMessage
from apps.push.services.contracts import PushSender
from core.container import container

__all__ = ["api", "as_user"]

ENABLED = {"VAPID_PUBLIC_KEY": "BPublicKey", "VAPID_PRIVATE_KEY": "private-key"}


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, PushMessage]] = []
        self.outcomes: dict[str, DeliveryOutcome] = {}

    def send(self, endpoint: Endpoint, message: PushMessage) -> DeliveryOutcome:
        self.sent.append((endpoint.url, message))
        return self.outcomes.get(endpoint.url, DeliveryOutcome.DELIVERED)


@pytest.fixture
def sender(settings) -> Iterator[RecordingSender]:
    settings.PUSH = ENABLED
    recording = RecordingSender()
    with container.override(PushSender, recording):
        yield recording


def device_payload(name: str = "a") -> dict[str, object]:
    return {
        "endpoint": f"https://push.example.com/{name}",
        "keys": {"p256dh": f"key-{name}", "auth": f"auth-{name}"},
        "user_agent": "Firefox 140",
    }
