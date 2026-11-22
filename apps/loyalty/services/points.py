from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from apps.loyalty.domain.errors import PointsUnavailable
from apps.loyalty.domain.points import (
    CLOSING_MONTHS,
    EARNINGS,
    ZERO,
    Balance,
    EntryKind,
    InvoiceStatement,
    Movement,
    add_months,
    referral_share,
    share,
)
from apps.loyalty.models import LoyaltySettings, PointsEntry
from apps.loyalty.repositories import LoyaltySettingsRepository, PointsRepository
from apps.loyalty.services.contracts import OrderLedger, Referrals, ReturnPolicy

CENT = Decimal("0.01")
HISTORY_SIZE = 30


class PointsService:
    def __init__(
        self,
        entries: PointsRepository,
        settings: LoyaltySettingsRepository,
        orders: OrderLedger,
        returns: ReturnPolicy,
        *,
        referrals: Referrals,
        clock: Callable[[], datetime],
    ) -> None:
        self._entries = entries
        self._settings = settings
        self._orders = orders
        self._returns = returns
        self._referrals = referrals
        self._clock = clock

    def balance(self, user_id: int) -> Balance:
        now = self._clock()
        settings = self._settings.current()
        available = sum((entry.remaining for entry in self._entries.credits(user_id, now)), ZERO)
        count, total = self._orders.delivered(user_id)
        closes_at = self._closes_at(settings)
        return Balance(
            eligible=self._spendable(settings, now),
            closes_at=closes_at if closes_at and closes_at > now else None,
            available=available,
            pending=self._entries.pending(user_id, now),
            next_expiry=self._valid_until(user_id, settings) if available > 0 else None,
            orders_count=count,
            orders_total=total,
            history=self._movements(user_id, now, limit=HISTORY_SIZE),
        )

    # every movement, newest first (personal data export)
    def history(self, user_id: int, *, limit: int) -> tuple[Movement, ...]:
        return self._movements(user_id, self._clock(), limit=limit)

    def _movements(self, user_id: int, now: datetime, *, limit: int) -> tuple[Movement, ...]:
        return tuple(
            Movement(
                kind=EntryKind(entry.kind),
                amount=entry.amount,
                at=entry.created_at,
                order_number=entry.order.number if entry.order else None,
                pending=entry.kind in EARNINGS and entry.available_at > now,
            )
            for entry in self._entries.recent(user_id, limit=limit)
        )

    # before delivery the order shows what it will earn, pending (loyalty policy)
    def invoice_statement(self, user_id: int, order_id: int) -> InvoiceStatement | None:
        settings = self._settings.current()
        now = self._clock()
        if not self._spendable(settings, now):
            return None
        purchase = self._orders.purchase(order_id)
        earned_entry = self._entries.for_order(order_id, EntryKind.EARN)
        if earned_entry is not None:
            earned = self.earned(order_id) or ZERO
            pending = earned_entry.available_at > now
        elif settings.points_enabled and purchase is not None:
            earned, pending = share(purchase.base, settings.points_percent), True
        else:
            # switched off: the order will earn nothing
            earned, pending = ZERO, False
        count, total = self._orders.delivered(user_id)
        return InvoiceStatement(
            earned=earned,
            earned_pending=pending,
            used=purchase.points_used if purchase else ZERO,
            available=sum((e.remaining for e in self._entries.credits(user_id, now)), ZERO),
            orders_count=count,
            orders_total=total,
            return_days=self._returns.return_days(),
        )

    # the client uses as many points as they like, up to the products' price (1 point = $1)
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        now = self._clock()
        if not self._spendable(self._settings.current(), now) or base <= 0:
            return ZERO
        credits = self._entries.credits(user_id, now, lock=lock)
        return min(sum((entry.remaining for entry in credits), ZERO), base)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        now = self._clock()
        left = amount
        for entry in self._entries.credits(user_id, now, lock=True):
            taken = min(entry.remaining, left)
            self._entries.use(entry, entry.remaining - taken)
            left -= taken
            if left == 0:
                break
        if left > 0:
            raise PointsUnavailable
        self._entries.add(
            user_id=user_id,
            order_id=order_id,
            kind=EntryKind.SPEND,
            amount=-amount,
            available_at=now,
        )

    # credited on delivery, spendable once the return period is over
    def earn(self, order_id: int, delivered_at: datetime) -> Decimal:
        settings = self._settings.current()
        purchase = self._orders.purchase(order_id)
        if purchase is None or self._entries.for_order(order_id, EntryKind.EARN):
            return ZERO
        if not self._eligible(settings):
            return ZERO
        amount = share(purchase.base, settings.points_percent)
        if amount <= 0:
            return ZERO
        available_at = delivered_at + timedelta(days=self._returns.return_days())
        self._entries.add(
            user_id=purchase.client_id,
            order_id=order_id,
            kind=EntryKind.EARN,
            amount=amount,
            remaining=amount,
            available_at=available_at,
        )
        return amount

    # the reseller who invited the client gets 0.3 % of the items for 12 months after the
    # invitation (reseller policy, 3.3); nothing when the order used points or a coupon
    def refer(self, order_id: int, delivered_at: datetime) -> Decimal:
        settings = self._settings.current()
        purchase = self._orders.purchase(order_id)
        if purchase is None or not self._eligible(settings) or not purchase.real_money_only:
            return ZERO
        if self._entries.for_order(order_id, EntryKind.REFERRAL):
            return ZERO
        referral = self._referrals.referral(purchase.client_id)
        placed_at = purchase.placed_at or delivered_at
        if referral is None or referral.reseller_id == purchase.client_id:
            return ZERO
        if not referral.since <= placed_at < add_months(referral.since, settings.referral_months):
            return ZERO
        amount = referral_share(purchase.base, settings.referral_percent)
        if amount <= 0:
            return ZERO
        self._entries.add(
            user_id=referral.reseller_id,
            order_id=order_id,
            kind=EntryKind.REFERRAL,
            amount=amount,
            remaining=amount,
            available_at=delivered_at + timedelta(days=self._returns.return_days()),
        )
        return amount

    # a cancelled or returned order loses what it still holds of its earning and gives back what
    # it used and was not refunded yet; earlier line returns already took their share
    def undo(self, order_id: int) -> None:
        earned = self._entries.for_order(order_id, EntryKind.EARN, lock=True)
        if earned and earned.remaining > 0:
            self._reverse(order_id, earned, earned.remaining)
        referred = self._entries.for_order(order_id, EntryKind.REFERRAL, lock=True)
        if referred and referred.remaining > 0:
            self._reverse(order_id, referred, referred.remaining, EntryKind.REFERRAL_REVERSAL)
        spent = self._entries.for_order(order_id, EntryKind.SPEND)
        if spent:
            self._refund(order_id, spent, self._unrefunded(order_id, spent))

    # units of one line came back: the earning shrinks in proportion to the real money returned
    # and the points spent on those units is given back
    def line_returned(self, order_id: int, paid: Decimal, points: Decimal) -> None:
        earned = self._entries.for_order(order_id, EntryKind.EARN, lock=True)
        purchase = self._orders.purchase(order_id)
        if earned and earned.remaining > 0 and purchase and purchase.base > 0 and paid > 0:
            part = (earned.amount * paid / purchase.base).quantize(CENT, rounding=ROUND_DOWN)
            self._reverse(order_id, earned, min(part, earned.remaining))
        referred = self._entries.for_order(order_id, EntryKind.REFERRAL, lock=True)
        if referred and referred.remaining > 0 and purchase and purchase.base > 0 and paid > 0:
            part = (referred.amount * paid / purchase.base).quantize(CENT, rounding=ROUND_DOWN)
            self._reverse(
                order_id, referred, min(part, referred.remaining), EntryKind.REFERRAL_REVERSAL
            )
        spent = self._entries.for_order(order_id, EntryKind.SPEND)
        if spent and points > 0:
            self._refund(order_id, spent, min(points, self._unrefunded(order_id, spent)))

    def _reverse(
        self,
        order_id: int,
        earned: PointsEntry,
        amount: Decimal,
        kind: EntryKind = EntryKind.REVERSAL,
    ) -> None:
        if amount <= 0:
            return
        self._entries.add(
            user_id=earned.user_id,
            order_id=order_id,
            kind=kind,
            amount=-amount,
            available_at=self._clock(),
        )
        self._entries.use(earned, earned.remaining - amount)

    def _unrefunded(self, order_id: int, spent: PointsEntry) -> Decimal:
        return -spent.amount - self._entries.total_for_order(order_id, EntryKind.REFUND)

    def _refund(self, order_id: int, spent: PointsEntry, amount: Decimal) -> None:
        if amount <= 0:
            return
        self._entries.add(
            user_id=spent.user_id,
            order_id=order_id,
            kind=EntryKind.REFUND,
            amount=amount,
            remaining=amount,
            available_at=self._clock(),
        )

    # the whole balance stays valid while the client buys at least once per validity period
    def expire(self) -> int:
        now = self._clock()
        settings = self._settings.current()
        expired = 0
        for user_id in self._entries.holders():
            valid_until = self._valid_until(user_id, settings)
            if valid_until is None or valid_until > now:
                continue
            for entry in self._entries.credits(user_id, now, lock=True, pending=True):
                self._entries.add(
                    user_id=entry.user_id,
                    kind=EntryKind.EXPIRY,
                    amount=-entry.remaining,
                    available_at=now,
                )
                self._entries.use(entry, ZERO)
                expired += 1
        return expired

    # each purchase restarts the count for the whole balance; before the first one, the earning
    def _valid_until(self, user_id: int, settings: LoyaltySettings) -> datetime | None:
        # the latest purchase, or a later credit of the client's own (points given back on a
        # cancelled order); a reseller's referral points restart nothing, unless they are all
        # the reseller has (no purchase yet)
        own = (EntryKind.EARN, EntryKind.REFUND)
        moments = [
            moment
            for moment in (
                self._orders.last_purchase(user_id),
                self._entries.last_credit(user_id, own),
            )
            if moment is not None
        ]
        if not moments:
            last_referral = self._entries.last_credit(user_id, (EntryKind.REFERRAL,))
            moments = [last_referral] if last_referral else []
        return add_months(max(moments), settings.points_validity_months) if moments else None

    def earned(self, order_id: int) -> Decimal | None:
        entry = self._entries.for_order(order_id, EntryKind.EARN)
        if entry is None:
            return None
        kept = entry.amount + self._entries.total_for_order(order_id, EntryKind.REVERSAL)
        return kept if kept > 0 else None

    # every client earns and uses points once the programme is on
    @staticmethod
    def _eligible(settings: LoyaltySettings) -> bool:
        return settings.points_enabled

    # switched off, the points stay usable for CLOSING_MONTHS (loyalty policy)
    @classmethod
    def _spendable(cls, settings: LoyaltySettings, now: datetime) -> bool:
        closes_at = cls._closes_at(settings)
        return settings.points_enabled or (closes_at is not None and now < closes_at)

    @staticmethod
    def _closes_at(settings: LoyaltySettings) -> datetime | None:
        if settings.points_enabled or settings.points_disabled_at is None:
            return None
        return add_months(settings.points_disabled_at, CLOSING_MONTHS)
