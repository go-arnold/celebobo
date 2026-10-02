from collections.abc import Callable
from datetime import datetime

from apps.sales.domain.commands import RecordPayout
from apps.sales.domain.errors import InvalidSaleDate, NotAReseller, PayoutExceedsDue
from apps.sales.models import Payout
from apps.sales.repositories import PayoutRepository
from apps.sales.services.commissions import CommissionService
from apps.sales.services.contracts import Sellers
from core.domain.actor import Actor, Role


class PayoutService:
    def __init__(
        self,
        payouts: PayoutRepository,
        commissions: CommissionService,
        sellers: Sellers,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._payouts = payouts
        self._commissions = commissions
        self._sellers = sellers
        self._clock = clock

    def record(self, actor: Actor, command: RecordPayout) -> Payout:
        reseller = self._sellers.profile(command.reseller_id)
        if reseller is None or reseller.role is not Role.RESELLER:
            raise NotAReseller
        due = self._commissions.balance(reseller.id)
        if command.amount > due:
            raise PayoutExceedsDue(str(due))
        paid_at = command.paid_at or self._clock()
        if paid_at > self._clock():
            raise InvalidSaleDate
        return self._payouts.create(
            reseller_id=reseller.id,
            amount=command.amount,
            note=" ".join(command.note.split()),
            paid_at=paid_at,
            paid_by_id=actor.user_id,
        )
