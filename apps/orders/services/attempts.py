from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.orders.domain.attempts import ATTEMPT_DAYS, working_days
from apps.orders.domain.commands import RecordAttempt
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import AttemptNotAllowed, NotAssignedToYou
from apps.orders.models import DeliveryAttempt, Order
from apps.orders.services.lifecycle import OrderLifecycleService, StatusChange
from core.domain.actor import Actor


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    attempt: DeliveryAttempt
    days: int
    # set when this attempt was the last one allowed
    cancellation: StatusChange | None


class DeliveryAttemptService:
    def __init__(self, lifecycle: OrderLifecycleService, *, clock: Callable[[], datetime]) -> None:
        self._lifecycle = lifecycle
        self._clock = clock

    def record(self, order: Order, actor: Actor, command: RecordAttempt) -> AttemptOutcome:
        if not (actor.is_staff or actor.owns(order.assigned_reseller_id)):
            raise NotAssignedToYou
        if order.order_status is not OrderStatus.SHIPPING:
            raise AttemptNotAllowed
        attempt = DeliveryAttempt.objects.create(
            order=order,
            reason=command.reason.value,
            note=" ".join(command.note.split())[:300],
            actor_id=actor.user_id,
            created_at=self._clock(),
        )
        days = working_days(
            timezone.localtime(at).date()
            for at in DeliveryAttempt.objects.filter(order=order).values_list(
                "created_at", flat=True
            )
        )
        cancellation = (
            self._lifecycle.fail_delivery(order, days=days) if days >= ATTEMPT_DAYS else None
        )
        return AttemptOutcome(attempt, days, cancellation)
