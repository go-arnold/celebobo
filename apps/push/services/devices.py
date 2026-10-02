from collections.abc import Callable, Iterable
from datetime import datetime

from apps.push.domain.errors import DeviceNotFound, TooManyDevices
from apps.push.domain.messages import (
    DeliveryOutcome,
    Endpoint,
    PushMessage,
    RegisterDevice,
    SendResult,
)
from apps.push.models import PushSubscription
from apps.push.repositories import SubscriptionRepository
from apps.push.services.contracts import PushSender


class DeviceService:
    def __init__(self, subscriptions: SubscriptionRepository, *, max_devices: int) -> None:
        self._subscriptions = subscriptions
        self._max_devices = max_devices

    def register(self, user_id: int, command: RegisterDevice) -> PushSubscription:
        if self._subscriptions.count_for(user_id) >= self._max_devices:
            known = {item.endpoint for item in self._subscriptions.for_user(user_id)}
            if command.endpoint not in known:
                raise TooManyDevices
        subscription, _ = self._subscriptions.upsert(
            command.endpoint,
            user_id=user_id,
            p256dh=command.p256dh,
            auth=command.auth,
            user_agent=command.user_agent[:255],
        )
        return subscription

    def remove(self, user_id: int, subscription_id: int) -> None:
        subscription = self._subscriptions.owned(user_id, subscription_id)
        if subscription is None:
            raise DeviceNotFound
        self._subscriptions.delete([subscription.pk])


class PushDispatcher:
    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        sender: PushSender,
        *,
        max_failures: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._subscriptions = subscriptions
        self._sender = sender
        self._max_failures = max_failures
        self._clock = clock

    def send(self, user_ids: Iterable[int], message: PushMessage) -> SendResult:
        outcomes: dict[DeliveryOutcome, list[int]] = {outcome: [] for outcome in DeliveryOutcome}
        for subscription in self._subscriptions.for_users(user_ids):
            endpoint = Endpoint(
                url=subscription.endpoint, p256dh=subscription.p256dh, auth=subscription.auth
            )
            outcomes[self._sender.send(endpoint, message)].append(subscription.pk)
        self._subscriptions.touch(outcomes[DeliveryOutcome.DELIVERED], self._clock())
        removed = self._subscriptions.delete(outcomes[DeliveryOutcome.GONE])
        removed += self._subscriptions.fail(
            outcomes[DeliveryOutcome.FAILED], limit=self._max_failures
        )
        return SendResult(
            delivered=len(outcomes[DeliveryOutcome.DELIVERED]),
            removed=removed,
            failed=len(outcomes[DeliveryOutcome.FAILED]),
        )
