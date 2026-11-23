from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.cash.domain.rules import Level
from apps.standing.domain import rules
from apps.standing.domain.commands import DecideSanction, ExplainSanction, OpenSanction
from apps.standing.domain.errors import (
    ExplanationClosed,
    HearingPending,
    InvalidSuspension,
    NotAReseller,
    SanctionClosed,
)
from apps.standing.domain.rules import SanctionKind, SanctionStatus
from apps.standing.models import ResellerLevel, Sanction
from apps.standing.repositories import StandingRepository
from apps.standing.services.contracts import Performance, ResellerAccounts
from core.domain.actor import Actor
from core.domain.errors import Forbidden


@dataclass(frozen=True, slots=True)
class LevelChange:
    reseller_id: int
    previous: Level
    level: Level


class LevelService:
    def __init__(
        self,
        standing: StandingRepository,
        performance: Performance,
        accounts: ResellerAccounts,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._standing = standing
        self._performance = performance
        self._accounts = accounts
        self._clock = clock

    def levels(self, reseller_ids: Iterable[int]) -> dict[int, Level]:
        return self._standing.levels(reseller_ids)

    # every active reseller's level from the last 3 months; a level can go down as well as up
    def review(self) -> list[LevelChange]:
        now = self._clock()
        resellers = [reseller_id for reseller_id, _name in self._accounts.active_resellers()]
        sales = self._performance.validated_sales(
            resellers,
            since=rules.months_before(now, rules.SALES_MONTHS),
            validated_before=now - timedelta(days=rules.VALIDATION_DAYS),
        )
        ratings = self._performance.ratings(resellers)
        changes = []
        for reseller_id in resellers:
            record = self._standing.level_record(reseller_id, for_update=True)
            previous = Level(record.level)
            level = rules.level_for(sales.get(reseller_id, Decimal(0)), ratings.get(reseller_id))
            record.level = level.value
            record.sales = sales.get(reseller_id, Decimal(0))
            record.rating = ratings.get(reseller_id)
            record.reviewed_at = now
            self._standing.save(record, fields=("level", "sales", "rating", "reviewed_at"))
            if level is not previous:
                changes.append(LevelChange(reseller_id, previous, level))
        return changes

    def record(self, reseller_id: int) -> ResellerLevel:
        return self._standing.level_record(reseller_id)


class SanctionService:
    def __init__(
        self,
        standing: StandingRepository,
        accounts: ResellerAccounts,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._standing = standing
        self._accounts = accounts
        self._clock = clock

    def open(self, actor: Actor, command: OpenSanction) -> Sanction:
        if not self._accounts.is_reseller(command.reseller_id):
            raise NotAReseller
        days = None
        if command.kind is SanctionKind.SUSPENSION:
            low, high = rules.SUSPENSION_DAYS
            if command.days is None or not low <= command.days <= high:
                raise InvalidSuspension
            days = command.days
        now = self._clock()
        sanction = self._standing.create_sanction(
            reseller_id=command.reseller_id,
            kind=command.kind.value,
            reason=command.reason.strip()[:2000],
            urgent=command.urgent,
            days=days,
            status=SanctionStatus.NOTIFIED.value,
            created_by_id=actor.user_id,
        )
        # a warning, or an urgent case, applies at once; otherwise 48 hours to explain
        if not command.kind.needs_hearing or command.urgent:
            return self._apply(actor, sanction, now)
        sanction.explain_until = now + timedelta(hours=rules.EXPLAIN_HOURS)
        self._standing.save_sanction(sanction, fields=("explain_until",))
        return sanction

    def explain(self, actor: Actor, sanction: Sanction, command: ExplainSanction) -> Sanction:
        if sanction.reseller_id != actor.user_id:
            raise Forbidden
        if SanctionStatus(sanction.status) is not SanctionStatus.NOTIFIED:
            raise SanctionClosed
        now = self._clock()
        if sanction.explain_until is not None and now > sanction.explain_until:
            raise ExplanationClosed
        sanction.explanation = command.explanation.strip()[:4000]
        sanction.explained_at = now
        self._standing.save_sanction(sanction, fields=("explanation", "explained_at"))
        return sanction

    # applied once the reseller explained or the 48 hours are over; dropped at any time
    def decide(self, actor: Actor, sanction: Sanction, command: DecideSanction) -> Sanction:
        if SanctionStatus(sanction.status) is not SanctionStatus.NOTIFIED:
            raise SanctionClosed
        now = self._clock()
        sanction.decision_note = command.note.strip()[:2000]
        if not command.apply:
            sanction.status = SanctionStatus.DROPPED.value
            sanction.decided_at = now
            sanction.decided_by_id = actor.user_id
            self._standing.save_sanction(
                sanction, fields=("status", "decided_at", "decided_by", "decision_note")
            )
            return sanction
        waiting = sanction.explained_at is None and (
            sanction.explain_until is not None and now <= sanction.explain_until
        )
        if waiting:
            raise HearingPending
        return self._apply(actor, sanction, now)

    def suspended(self, reseller_ids: Iterable[int]) -> dict[int, datetime]:
        return self._standing.suspended_until(reseller_ids, self._clock())

    def _apply(self, actor: Actor, sanction: Sanction, now: datetime) -> Sanction:
        sanction.status = SanctionStatus.APPLIED.value
        sanction.decided_at = now
        sanction.decided_by_id = actor.user_id
        sanction.starts_at = now
        if sanction.kind == SanctionKind.SUSPENSION.value and sanction.days:
            sanction.ends_at = now + timedelta(days=sanction.days)
        self._standing.save_sanction(
            sanction,
            fields=("status", "decided_at", "decided_by", "starts_at", "ends_at", "decision_note"),
        )
        if sanction.kind == SanctionKind.EXCLUSION.value:
            self._accounts.deactivate(actor, sanction.reseller_id)
        return sanction


def local_day(moment: datetime) -> str:
    return f"{timezone.localtime(moment):%d/%m/%Y}"
