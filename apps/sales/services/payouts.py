from collections.abc import Callable
from datetime import datetime

from apps.sales.domain.commands import RecordPayout
from apps.sales.domain.errors import (
    InvalidSaleDate,
    PayoutExceedsDue,
    StatementNotFound,
    StatementNotPayable,
)
from apps.sales.domain.payouts import StatementStatus
from apps.sales.models import Payout, PayoutStatement
from apps.sales.repositories import PayoutRepository, StatementRepository
from core.domain.actor import Actor


class PayoutService:
    def __init__(
        self,
        payouts: PayoutRepository,
        statements: StatementRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._payouts = payouts
        self._statements = statements
        self._clock = clock

    # an admin pays a prepared statement in full; never more than what is due right now
    def record(self, actor: Actor, command: RecordPayout) -> tuple[Payout, PayoutStatement]:
        statement = self._statements.lock(command.statement_id)
        if statement is None:
            raise StatementNotFound
        if statement.status != StatementStatus.PREPARED.value:
            raise StatementNotPayable
        now = self._clock()
        due = self._statements.due(statement.reseller_id, now)
        if statement.total > due:
            raise PayoutExceedsDue(str(due))
        paid_at = command.paid_at or now
        if paid_at > now:
            raise InvalidSaleDate
        payout = self._payouts.create(
            reseller_id=statement.reseller_id,
            amount=statement.total,
            note=" ".join(command.note.split()),
            paid_at=paid_at,
            paid_by_id=actor.user_id,
        )
        statement.payout = payout
        statement.status = StatementStatus.PAID.value
        self._statements.save(statement, fields=("payout", "status"))
        return payout, statement
