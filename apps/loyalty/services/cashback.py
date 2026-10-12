from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from apps.loyalty.domain.cashback import ZERO, Balance, EntryKind, share
from apps.loyalty.domain.errors import CashbackUnavailable
from apps.loyalty.domain.membership import add_months
from apps.loyalty.models import LoyaltySettings
from apps.loyalty.repositories import (
    CashbackRepository,
    LoyaltySettingsRepository,
    MembershipRepository,
)
from apps.loyalty.services.contracts import OrderLedger, ReturnPolicy


class CashbackService:
    def __init__(
        self,
        entries: CashbackRepository,
        settings: LoyaltySettingsRepository,
        memberships: MembershipRepository,
        orders: OrderLedger,
        returns: ReturnPolicy,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._entries = entries
        self._settings = settings
        self._memberships = memberships
        self._orders = orders
        self._returns = returns
        self._clock = clock

    def balance(self, user_id: int) -> Balance:
        now = self._clock()
        credits = self._entries.credits(user_id, now)
        return Balance(
            eligible=self._eligible(self._settings.current(), user_id),
            available=sum((entry.remaining for entry in credits), ZERO),
            pending=self._entries.pending(user_id, now),
            next_expiry=min(
                (entry.expires_at for entry in credits if entry.expires_at), default=None
            ),
        )

    # how much of the balance an order of `base` (products after discounts) may use
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        settings = self._settings.current()
        if not self._eligible(settings, user_id) or base <= 0:
            return ZERO
        credits = self._entries.credits(user_id, self._clock(), lock=lock)
        available = sum((entry.remaining for entry in credits), ZERO)
        if available < settings.cashback_min_balance:
            return ZERO
        return min(available, share(base, Decimal(settings.cashback_max_share)))

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
            raise CashbackUnavailable
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
        if not self._eligible(settings, purchase.client_id):
            return ZERO
        amount = share(purchase.base, settings.cashback_percent)
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
            expires_at=add_months(available_at, settings.cashback_validity_months),
        )
        return amount

    # a cancelled or returned order loses what it earned and gives back what it used
    def undo(self, order_id: int) -> None:
        now = self._clock()
        earned = self._entries.for_order(order_id, EntryKind.EARN, lock=True)
        if (
            earned
            and earned.remaining > 0
            and not self._entries.for_order(order_id, EntryKind.REVERSAL)
        ):
            self._entries.add(
                user_id=earned.user_id,
                order_id=order_id,
                kind=EntryKind.REVERSAL,
                amount=-earned.remaining,
                available_at=now,
            )
            self._entries.use(earned, ZERO)
        spent = self._entries.for_order(order_id, EntryKind.SPEND)
        if spent and not self._entries.for_order(order_id, EntryKind.REFUND):
            settings = self._settings.current()
            self._entries.add(
                user_id=spent.user_id,
                order_id=order_id,
                kind=EntryKind.REFUND,
                amount=-spent.amount,
                remaining=-spent.amount,
                available_at=now,
                expires_at=add_months(now, settings.cashback_validity_months),
            )

    def expire(self) -> int:
        now = self._clock()
        expired = self._entries.expired(now)
        for entry in expired:
            self._entries.add(
                user_id=entry.user_id,
                kind=EntryKind.EXPIRY,
                amount=-entry.remaining,
                available_at=now,
            )
            self._entries.use(entry, ZERO)
        return len(expired)

    def earned(self, order_id: int) -> Decimal | None:
        entry = self._entries.for_order(order_id, EntryKind.EARN)
        if entry is None or self._entries.for_order(order_id, EntryKind.REVERSAL):
            return None
        return entry.amount

    def _eligible(self, settings: LoyaltySettings, user_id: int) -> bool:
        if not settings.cashback_enabled:
            return False
        return not settings.cashback_members_only or self._memberships.active(
            user_id, self._clock()
        )
