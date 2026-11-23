from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from decimal import Decimal

from apps.cash.domain.commands import RecordRemittance
from apps.cash.domain.errors import NotAReseller, RemittanceExceedsHeld
from apps.cash.domain.rules import REMIT_HOURS, ZERO, CashPosition, Level
from apps.cash.models import CashCollection, CashRemittance
from apps.cash.repositories import CashRepository
from apps.cash.services.contracts import ResellerLevels, Resellers
from apps.orders.domain.read_models import CashableOrder
from core.domain.actor import Actor


class CashService:
    def __init__(
        self,
        cash: CashRepository,
        levels: ResellerLevels,
        resellers: Resellers,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._cash = cash
        self._levels = levels
        self._resellers = resellers
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    # the order is paid or delivered by its reseller: the money they collected is now due (once
    # per order; nothing for a pickup, paid at the shop)
    def collect(self, order: CashableOrder) -> CashCollection | None:
        if order.pickup or order.reseller_id is None or order.total <= 0:
            return None
        if self._cash.collection_of(order.order_id) is not None:
            return None
        now = self._clock()
        return self._cash.create_collection(
            reseller_id=order.reseller_id,
            order_id=order.order_id,
            order_number=order.number,
            amount=order.total,
            collected_at=now,
            due_at=now + timedelta(hours=REMIT_HOURS),
        )

    # cancelled before any remittance: the reseller gave the money back to the client, nothing is
    # owed; once partly remitted, staff settle it by hand
    def void(self, order_id: int) -> bool:
        collection = self._cash.collection_of(order_id, for_update=True)
        if collection is None or collection.voided_at is not None or collection.covered > 0:
            return False
        collection.voided_at = self._clock()
        self._cash.save(collection, fields=("voided_at",))
        return True

    # a remittance covers the oldest collections first; never more than the reseller holds
    def remit(self, actor: Actor, command: RecordRemittance) -> CashRemittance:
        if not self._resellers.is_reseller(command.reseller_id):
            raise NotAReseller
        open_collections = self._cash.open_collections(command.reseller_id, for_update=True)
        held = sum((row.amount - row.covered for row in open_collections), ZERO)
        if command.amount > held:
            raise RemittanceExceedsHeld(str(held))
        left = command.amount
        for collection in open_collections:
            if left <= 0:
                break
            part = min(collection.amount - collection.covered, left)
            collection.covered += part
            self._cash.save(collection, fields=("covered",))
            left -= part
        return self._cash.create_remittance(
            reseller_id=command.reseller_id,
            amount=command.amount,
            reference=" ".join(command.reference.split())[:80],
            received_at=command.received_at or self._clock(),
            recorded_by_id=actor.user_id,
        )

    def position(self, reseller_id: int) -> CashPosition:
        return self.positions([reseller_id])[reseller_id]

    def positions(self, reseller_ids: Iterable[int]) -> dict[int, CashPosition]:
        ids = list(dict.fromkeys(reseller_ids))
        now = self._clock()
        held: dict[int, Decimal] = dict.fromkeys(ids, ZERO)
        overdue: dict[int, Decimal] = dict.fromkeys(ids, ZERO)
        oldest: dict[int, datetime] = {}
        for row in self._cash.open_collections_of(ids):
            left = row.amount - row.covered
            held[row.reseller_id] += left
            if row.due_at <= now:
                overdue[row.reseller_id] += left
                oldest.setdefault(row.reseller_id, row.due_at)
        levels = self._levels.levels(ids)
        positions = {}
        for reseller_id in ids:
            level = levels.get(reseller_id, Level.BEGINNER)
            positions[reseller_id] = CashPosition(
                reseller_id=reseller_id,
                level=level,
                cap=level.cash_cap,
                held=held[reseller_id],
                overdue=overdue[reseller_id],
                oldest_due=oldest.get(reseller_id),
            )
        return positions
