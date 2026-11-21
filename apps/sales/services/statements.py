from collections.abc import Callable
from datetime import date, datetime, time

from django.utils import timezone

from apps.orders.domain.enums import DeliveryMethod
from apps.sales.domain.payouts import (
    DeliveryCreditKind,
    PayoutCalendar,
    StatementStatus,
    payable,
)
from apps.sales.domain.rules import ZERO
from apps.sales.models import PayoutStatement
from apps.sales.repositories import DeliveryCreditRepository, StatementRepository
from apps.sales.services.contracts import OrderBook, Sellers
from core.domain.actor import Role

DELIVERY_FEE_NOTE = "Frais de livraison"


def start_of(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


class StatementService:
    """Prepares, on each payout date, what every reseller is paid (reseller policy, 5)."""

    def __init__(
        self,
        statements: StatementRepository,
        *,
        clock: Callable[[], datetime],
        calendar: PayoutCalendar | None = None,
    ) -> None:
        self._statements = statements
        self._clock = clock
        self._calendar = calendar or PayoutCalendar()

    # the payout date being prepared today, if today is one
    def payout_date(self) -> date | None:
        today = timezone.localdate(self._clock())
        return today if self._calendar.is_payout_day(today) else None

    def next_payout_date(self) -> date:
        return self._calendar.next(timezone.localdate(self._clock()))

    def reseller_ids(self) -> list[int]:
        return self._statements.reseller_ids()

    # everything validated before the payout date and not settled yet, delivery fees included;
    # an unpaid statement of an earlier date is replaced. Below the threshold, nothing is
    # prepared and the balance rolls over to the next date.
    def prepare(self, reseller_id: int, payout_date: date) -> PayoutStatement | None:
        if self._statements.exists_for(reseller_id, payout_date):
            return None
        now = self._clock()
        for earlier in self._statements.prepared(reseller_id):
            if earlier.payout_date < payout_date:
                self._cancel(earlier, now)
        entries, credits = self._statements.unsettled(reseller_id, start_of(payout_date))
        commissions = sum((entry.amount for entry in entries), ZERO)
        fees = sum((credit.amount for credit in credits), ZERO)
        if not payable(commissions + fees):
            return None
        statement = self._statements.create(
            reseller_id=reseller_id,
            payout_date=payout_date,
            commissions=commissions,
            delivery_fees=fees,
            total=commissions + fees,
            prepared_at=now,
        )
        self._statements.settle(statement, entries, credits)
        return statement

    # a sale or an order of a prepared statement changed (refund, return, edit): its new entries
    # join the statement, whose totals follow; a statement left with nothing to pay is dropped
    def refresh(self, reseller_id: int) -> None:
        for statement in self._statements.prepared(reseller_id):
            self._statements.attach_reversals(statement)
            commissions, fees = self._statements.totals(statement)
            if commissions + fees <= ZERO:
                self._cancel(statement, self._clock())
                continue
            statement.commissions = commissions
            statement.delivery_fees = fees
            statement.total = commissions + fees
            self._statements.save(statement, fields=("commissions", "delivery_fees", "total"))

    def _cancel(self, statement: PayoutStatement, now: datetime) -> None:
        self._statements.release(statement)
        statement.status = StatementStatus.CANCELLED.value
        statement.cancelled_at = now
        self._statements.save(statement, fields=("status", "cancelled_at"))


class DeliveryCreditService:
    """The reseller remits everything collected; the delivery fee of each order they delivered
    comes back to them on their payout, as its own line (owner's decision of 18 Nov 2026)."""

    def __init__(
        self, credits: DeliveryCreditRepository, books: OrderBook, sellers: Sellers
    ) -> None:
        self._credits = credits
        self._books = books
        self._sellers = sellers

    # nothing for a pickup, a free delivery, or an order no reseller delivered
    def credit(self, order_id: int, delivered_at: datetime) -> int | None:
        delivery = self._books.delivery(order_id)
        if delivery is None or delivery.reseller_id is None:
            return None
        if delivery.delivery_method is not DeliveryMethod.DELIVERY or delivery.shipping_fee <= 0:
            return None
        reseller = self._sellers.profile(delivery.reseller_id)
        if reseller is None or reseller.role is not Role.RESELLER:
            return None
        if self._credits.for_order(order_id, DeliveryCreditKind.CREDIT.value):
            return None
        self._credits.add(
            reseller_id=reseller.id,
            order_id=order_id,
            order_number=delivery.number,
            kind=DeliveryCreditKind.CREDIT.value,
            amount=delivery.shipping_fee,
            note=DELIVERY_FEE_NOTE,
            available_at=delivery.delivered_at or delivered_at,
        )
        return reseller.id

    # a delivered order cannot be cancelled today; should it happen, the fee is taken back
    def reverse(self, order_id: int, *, note: str) -> int | None:
        credit = self._credits.for_order(order_id, DeliveryCreditKind.CREDIT.value)
        if credit is None or self._credits.for_order(order_id, DeliveryCreditKind.REVERSAL.value):
            return None
        self._credits.add(
            reseller_id=credit.reseller_id,
            order_id=order_id,
            order_number=credit.order_number,
            kind=DeliveryCreditKind.REVERSAL.value,
            amount=-credit.amount,
            note=note,
            available_at=credit.available_at,
        )
        return credit.reseller_id
