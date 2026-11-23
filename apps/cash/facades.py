from django.db import transaction

from apps.cash.adapters.gateways import AccountsResellers
from apps.cash.domain.commands import RecordRemittance
from apps.cash.domain.errors import NotAReseller
from apps.cash.domain.events import CashOverdue, CashRemitted
from apps.cash.domain.read_models import CashSummary, CollectionView, RemittanceView
from apps.cash.domain.rules import CashPosition
from apps.cash.selectors import CashSelector
from apps.cash.services.cash import CashService
from apps.orders.selectors import cashable_order
from core.domain.actor import Actor
from core.domain.errors import Forbidden
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class CashFacade:
    def __init__(
        self,
        *,
        cash: CashService,
        selector: CashSelector,
        resellers: AccountsResellers,
        publisher: EventPublisher,
    ) -> None:
        self._cash = cash
        self._selector = selector
        self._resellers = resellers
        self._publisher = publisher

    # the order is paid or delivered: its reseller collected the money
    def order_paid(self, order_id: int) -> None:
        order = cashable_order(order_id)
        if order is not None:
            self._cash.collect(order)

    def order_cancelled(self, order_id: int) -> None:
        self._cash.void(order_id)

    # a reseller sees their own; staff (`cash.manage`) any reseller's
    def summary(self, actor: Actor, reseller_id: int | None) -> CashSummary:
        target = reseller_id if actor.is_staff and reseller_id else actor.user_id
        if target is None:
            raise Forbidden
        if not self._resellers.is_reseller(target):
            raise NotAReseller
        position = self._cash.position(target)
        now = self._cash.now()
        return self._summary(
            position,
            self._resellers.names([target]).get(target, ""),
            collections=tuple(
                CollectionView(
                    order_id=row.order_id,
                    order_number=row.order_number,
                    amount=row.amount,
                    left=row.amount - row.covered,
                    collected_at=row.collected_at,
                    due_at=row.due_at,
                    overdue=row.due_at <= now,
                )
                for row in self._selector.open_collections(target)
            ),
            remittances=tuple(
                RemittanceView(
                    amount=row.amount, reference=row.reference, received_at=row.received_at
                )
                for row in self._selector.remittances(target)
            ),
        )

    # staff: every reseller who holds cash, the overdue and blocked first
    def overview(self) -> list[CashSummary]:
        ids = self._selector.holders()
        names = self._resellers.names(ids)
        rows = [
            self._summary(position, names.get(reseller_id, ""))
            for reseller_id, position in self._cash.positions(ids).items()
        ]
        return sorted(rows, key=lambda row: (row.blocked_reason is None, -row.held))

    # hourly: a reseller whose collected money is past its 24 hours is told, once per order
    def remind_overdue(self) -> int:
        with transaction.atomic():
            due = self._cash.remind()
            for collection in due:
                self._publisher.publish(
                    CashOverdue(
                        reseller_id=collection.reseller_id,
                        order_number=collection.order_number,
                        amount=collection.amount - collection.covered,
                    )
                )
        return len(due)

    def remit(self, actor: Actor, command: RecordRemittance) -> CashSummary:
        with transaction.atomic():
            remittance = self._cash.remit(actor, command)
            self._publisher.publish(
                CashRemitted(
                    reseller_id=remittance.reseller_id,
                    amount=remittance.amount,
                    actor_id=actor.user_id,
                )
            )
        return self.summary(actor, command.reseller_id)

    @staticmethod
    def _summary(
        position: CashPosition,
        name: str,
        *,
        collections: tuple[CollectionView, ...] = (),
        remittances: tuple[RemittanceView, ...] = (),
    ) -> CashSummary:
        return CashSummary(
            reseller_id=position.reseller_id,
            reseller_name=name,
            level=position.level,
            cap=position.cap,
            held=position.held,
            overdue=position.overdue,
            oldest_due=position.oldest_due,
            blocked_reason=position.blocked_reason,
            collections=collections,
            remittances=remittances,
        )
