from django.db import transaction
from django.utils import timezone

from apps.cash.domain.rules import Level
from apps.standing.domain import rules
from apps.standing.domain.commands import DecideSanction, ExplainSanction, OpenSanction
from apps.standing.domain.errors import NotAReseller, SanctionNotFound
from apps.standing.domain.events import LevelChanged, SanctionUpdated
from apps.standing.domain.read_models import SanctionView, Standing
from apps.standing.domain.rules import SanctionKind, SanctionStatus
from apps.standing.models import Sanction
from apps.standing.repositories import StandingRepository
from apps.standing.selectors import SanctionSelector
from apps.standing.services.contracts import ResellerAccounts
from apps.standing.services.standing import LevelService, SanctionService, local_day
from core.domain.actor import Actor
from core.domain.errors import Forbidden
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


def sanction_message(sanction: Sanction) -> str:
    kind = SanctionKind(sanction.kind)
    status = SanctionStatus(sanction.status)
    if status is SanctionStatus.DROPPED:
        return f"{kind.label} envisagée : abandonnée."
    if status is SanctionStatus.NOTIFIED:
        until = local_day(sanction.explain_until) if sanction.explain_until else ""
        return (
            f"{kind.label} envisagée. Motif : {sanction.reason} Vous pouvez vous expliquer "
            f"jusqu'au {until} dans votre espace revendeur."
        )
    if kind is SanctionKind.SUSPENSION and sanction.ends_at is not None:
        return (
            f"Suspension jusqu'au {local_day(sanction.ends_at)} : vous ne recevez plus de "
            f"nouvelles commandes. Motif : {sanction.reason}"
        )
    if kind is SanctionKind.EXCLUSION:
        return f"Exclusion : votre compte revendeur est fermé. Motif : {sanction.reason}"
    return f"Avertissement écrit. Motif : {sanction.reason}"


@logged_facade
class StandingFacade:
    def __init__(
        self,
        *,
        levels: LevelService,
        sanctions: SanctionService,
        repository: StandingRepository,
        selector: SanctionSelector,
        accounts: ResellerAccounts,
        publisher: EventPublisher,
    ) -> None:
        self._levels = levels
        self._sanctions = sanctions
        self._repository = repository
        self._selector = selector
        self._accounts = accounts
        self._publisher = publisher

    # a reseller sees their own standing; staff any reseller's
    def standing(self, actor: Actor, reseller_id: int | None) -> Standing:
        target = reseller_id if actor.is_staff and reseller_id else actor.user_id
        if target is None:
            raise Forbidden
        if not self._accounts.is_reseller(target):
            raise NotAReseller
        record = self._levels.record(target)
        level = Level(record.level)
        upper = [
            t
            for t in reversed(rules.THRESHOLDS)
            if list(Level).index(t.level) > list(Level).index(level)
        ]
        nxt = upper[0] if upper else None
        return Standing(
            reseller_id=target,
            reseller_name=self._accounts.names([target]).get(target, ""),
            level=level,
            advantages=rules.ADVANTAGES[level],
            sales=record.sales,
            rating=record.rating,
            reviewed_at=record.reviewed_at,
            next_level=nxt.level if nxt else None,
            next_sales=nxt.sales if nxt else None,
            next_rating=nxt.rating if nxt else None,
            suspended_until=self._sanctions.suspended([target]).get(target),
            sanctions=tuple(self._selector.of_reseller(target)),
        )

    def review(self) -> int:
        with transaction.atomic():
            changes = self._levels.review()
            for change in changes:
                self._publisher.publish(
                    LevelChanged(
                        reseller_id=change.reseller_id,
                        previous=change.previous.value,
                        level=change.level.value,
                        level_label=change.level.label,
                    )
                )
        return len(changes)

    # daily task: the review runs on the first day of each quarter
    def review_if_due(self) -> int:
        if not rules.is_review_day(timezone.localdate()):
            return 0
        return self.review()

    def sanctions(
        self, *, reseller_id: int | None, status: SanctionStatus | None, offset: int, limit: int
    ) -> tuple[list[SanctionView], int]:
        return self._selector.page(
            reseller_id=reseller_id, status=status, offset=offset, limit=limit
        )

    def open(self, actor: Actor, command: OpenSanction) -> SanctionView:
        with transaction.atomic():
            sanction = self._sanctions.open(actor, command)
            self._announce(sanction, actor)
        return self._selector.one(sanction.pk)

    def explain(self, actor: Actor, sanction_id: int, command: ExplainSanction) -> SanctionView:
        with transaction.atomic():
            sanction = self._locked(sanction_id)
            self._sanctions.explain(actor, sanction, command)
        return self._selector.one(sanction_id)

    def decide(self, actor: Actor, sanction_id: int, command: DecideSanction) -> SanctionView:
        with transaction.atomic():
            sanction = self._sanctions.decide(actor, self._locked(sanction_id), command)
            self._announce(sanction, actor)
        return self._selector.one(sanction_id)

    def _locked(self, sanction_id: int) -> Sanction:
        sanction = self._repository.sanction(sanction_id, for_update=True)
        if sanction is None:
            raise SanctionNotFound
        return sanction

    def _announce(self, sanction: Sanction, actor: Actor) -> None:
        self._publisher.publish(
            SanctionUpdated(
                sanction_id=sanction.pk,
                reseller_id=sanction.reseller_id,
                kind=sanction.kind,
                status=sanction.status,
                message=sanction_message(sanction),
                actor_id=actor.user_id,
            )
        )
