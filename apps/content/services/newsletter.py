from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.accounts.domain.normalization import normalize_email
from apps.content.domain.errors import UnknownSubscription
from apps.content.models import Subscriber
from apps.content.repositories import SubscriberRepository


@dataclass(frozen=True, slots=True)
class SubscriptionResult:
    subscriber: Subscriber
    created: bool


class NewsletterService:
    def __init__(self, subscribers: SubscriberRepository, *, clock: Callable[[], datetime]) -> None:
        self._subscribers = subscribers
        self._clock = clock

    def subscribe(self, email: str, *, source: str) -> SubscriptionResult:
        address = normalize_email(email)
        existing = self._subscribers.by_email(address, for_update=True)
        if existing is not None:
            if existing.is_active:
                return SubscriptionResult(existing, created=False)
            existing.unsubscribed_at = None
            existing.source = source or existing.source
            self._subscribers.save(existing, fields=("unsubscribed_at", "source"))
            return SubscriptionResult(existing, created=True)
        try:
            with transaction.atomic():
                subscriber = self._subscribers.create(email=address, source=source)
        except IntegrityError:
            raced = self._subscribers.by_email(address)
            if raced is None:
                raise
            return SubscriptionResult(raced, created=False)
        return SubscriptionResult(subscriber, created=True)

    def get(self, subscriber_id: int) -> Subscriber | None:
        return self._subscribers.get(subscriber_id)

    def unsubscribe(self, token: UUID) -> Subscriber:
        subscriber = self._subscribers.by_token(token)
        if subscriber is None:
            raise UnknownSubscription
        self._stop(subscriber)
        return subscriber

    # the account's marketing consent was withdrawn: no more e-mail offers to that address
    def unsubscribe_email(self, email: str) -> Subscriber | None:
        subscriber = self._subscribers.by_email(normalize_email(email), for_update=True)
        if subscriber is not None:
            self._stop(subscriber)
        return subscriber

    def _stop(self, subscriber: Subscriber) -> None:
        if subscriber.is_active:
            subscriber.unsubscribed_at = self._clock()
            self._subscribers.save(subscriber, fields=("unsubscribed_at",))
