from datetime import datetime
from decimal import Decimal

from django.db import transaction

from apps.loyalty.domain.events import LoyaltySettingsChanged
from apps.loyalty.domain.points import Balance, InvoiceStatement
from apps.loyalty.domain.settings import LoyaltySettingsChanges, Programmes
from apps.loyalty.selectors import to_programmes
from apps.loyalty.services.points import PointsService
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


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class PointsFacade:
    def __init__(self, *, points: PointsService) -> None:
        self._points = points

    def mine(self, actor: Actor) -> Balance:
        return self._points.balance(_user_id(actor))

    def invoice_statement(self, user_id: int, order_id: int) -> InvoiceStatement | None:
        return self._points.invoice_statement(user_id, order_id)

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return self._points.usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        self._points.spend(user_id, order_id, amount)

    def earned(self, order_id: int) -> Decimal | None:
        return self._points.earned(order_id)

    def delivered(self, order_id: int, delivered_at: datetime) -> None:
        with transaction.atomic():
            self._points.earn(order_id, delivered_at)
            self._points.refer(order_id, delivered_at)

    def undone(self, order_id: int) -> None:
        with transaction.atomic():
            self._points.undo(order_id)

    def line_returned(self, order_id: int, paid: Decimal, points: Decimal) -> None:
        with transaction.atomic():
            self._points.line_returned(order_id, paid, points)

    def expire(self) -> int:
        with transaction.atomic():
            return self._points.expire()
