from typing import Protocol

from apps.push.domain.messages import DeliveryOutcome, Endpoint, PushMessage


class PushSender(Protocol):
    def send(self, endpoint: Endpoint, message: PushMessage) -> DeliveryOutcome: ...
