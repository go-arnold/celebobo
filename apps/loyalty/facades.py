from datetime import datetime
from decimal import Decimal

from django.db import transaction

from apps.loyalty.domain.cashback import Balance
from apps.loyalty.domain.events import LoyaltyRuleChanged, LoyaltySettingsChanged
from apps.loyalty.domain.points import PointBalance, PointTransactionView
from apps.loyalty.domain.rules import LoyaltyRuleDTO
from apps.loyalty.domain.settings import LoyaltySettingsChanges, Programmes
from apps.loyalty.selectors import to_programmes
from apps.loyalty.services.cashback import CashbackService
from apps.loyalty.services.points import PointService
from apps.loyalty.services.rules import LoyaltyRuleService
from apps.loyalty.services.settings import LoyaltySettingsService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class LoyaltyFacade:
    def __init__(self, *, settings: LoyaltySettingsService, publisher: EventPublisher) -> None:
        self._settings = settings
        self._publisher = publisher

    def programmes(self) -> Programmes:
        return to_programmes(self._settings.current())

    def update(self, actor: Actor, changes: LoyaltySettingsChanges) -> Programmes:
        with transaction.atomic():
            if self._settings.update(changes):
                self._publisher.publish(LoyaltySettingsChanged(actor_id=actor.user_id))
        return self.programmes()


@logged_facade
class PointsFacade:
    def __init__(self, *, points: PointService) -> None:
        self._points = points

    def mine(self, actor: Actor) -> PointBalance:
        return self._points.balance(_user_id(actor))

    def transactions(
        self, actor: Actor, *, offset: int, limit: int
    ) -> tuple[list[PointTransactionView], int]:
        return self._points.transactions(_user_id(actor), offset=offset, limit=limit)


@logged_facade
class LoyaltyRuleFacade:
    def __init__(self, *, rules: LoyaltyRuleService) -> None:
        self._rules = rules

    def list(self) -> list[LoyaltyRuleDTO]:
        return self._rules.list()

    def create(
        self,
        actor: Actor,
        *,
        name: str,
        trigger: str,
        condition: dict,
        points_value: int,
        is_active: bool = True,
        max_per_user: int | None = None,
        max_per_day: int | None = None,
        cooldown_days: int | None = None,
    ) -> LoyaltyRuleDTO:
        with transaction.atomic():
            rule = self._rules.create(
                name=name, trigger=trigger, condition=condition, points_value=points_value,
                is_active=is_active, max_per_user=max_per_user, max_per_day=max_per_day,
                cooldown_days=cooldown_days,
            )
            self._publisher.publish(
                LoyaltyRuleChanged(rule_id=rule.id, action="created", actor_id=actor.user_id)
            )
        return self._rules.to_dto(rule)

    def update(self, actor: Actor, rule_id: int, **changes: object) -> LoyaltyRuleDTO:
        with transaction.atomic():
            rule = self._rules.update(rule_id, **changes)
            self._publisher.publish(
                LoyaltyRuleChanged(rule_id=rule.id, action="updated", actor_id=actor.user_id)
            )
        return self._rules.to_dto(rule)

    def delete(self, actor: Actor, rule_id: int) -> None:
        with transaction.atomic():
            self._rules.delete(rule_id)
            self._publisher.publish(
                LoyaltyRuleChanged(rule_id=rule_id, action="deleted", actor_id=actor.user_id)
            )


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class CashbackFacade:
    def __init__(self, *, cashback: CashbackService) -> None:
        self._cashback = cashback

    def mine(self, actor: Actor) -> Balance:
        return self._cashback.balance(_user_id(actor))

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return self._cashback.usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        self._cashback.spend(user_id, order_id, amount)

    def earned(self, order_id: int) -> Decimal | None:
        return self._cashback.earned(order_id)

    def delivered(self, order_id: int, delivered_at: datetime) -> None:
        with transaction.atomic():
            self._cashback.earn(order_id, delivered_at)

    def undone(self, order_id: int) -> None:
        with transaction.atomic():
            self._cashback.undo(order_id)

    def expire(self) -> int:
        with transaction.atomic():
            return self._cashback.expire()
