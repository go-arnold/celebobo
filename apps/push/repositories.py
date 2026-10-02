from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.db.models import F

from apps.push.models import PushSubscription


class SubscriptionRepository:
    def for_users(self, user_ids: Iterable[int]) -> list[PushSubscription]:
        return list(PushSubscription.objects.filter(user_id__in=list(user_ids)))

    def for_user(self, user_id: int) -> list[PushSubscription]:
        return list(PushSubscription.objects.filter(user_id=user_id))

    def count_for(self, user_id: int) -> int:
        return PushSubscription.objects.filter(user_id=user_id).count()

    def upsert(self, endpoint: str, **fields: Any) -> tuple[PushSubscription, bool]:
        return PushSubscription.objects.update_or_create(
            endpoint=endpoint, defaults={**fields, "failures": 0}
        )

    def owned(self, user_id: int, subscription_id: int) -> PushSubscription | None:
        return PushSubscription.objects.filter(user_id=user_id, pk=subscription_id).first()

    def delete(self, subscription_ids: Iterable[int]) -> int:
        deleted, _ = PushSubscription.objects.filter(pk__in=list(subscription_ids)).delete()
        return deleted

    def touch(self, subscription_ids: Iterable[int], when: datetime) -> None:
        PushSubscription.objects.filter(pk__in=list(subscription_ids)).update(
            last_used_at=when, failures=0
        )

    def fail(self, subscription_ids: Iterable[int], *, limit: int) -> int:
        ids = list(subscription_ids)
        PushSubscription.objects.filter(pk__in=ids).update(failures=F("failures") + 1)
        dropped, _ = PushSubscription.objects.filter(pk__in=ids, failures__gte=limit).delete()
        return dropped
