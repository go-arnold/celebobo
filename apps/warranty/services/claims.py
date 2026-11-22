from collections.abc import Callable
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.orders.domain import serials
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import ClaimableLine
from apps.warranty.domain import rules
from apps.warranty.domain.commands import (
    AnswerClaim,
    DiagnoseClaim,
    FinishRepair,
    ReceiveClaim,
    SubmitClaim,
)
from apps.warranty.domain.errors import (
    ClaimAlreadyOpen,
    ClaimStepNotAllowed,
    ClaimWindowClosed,
    LineNotClaimable,
    OutcomeNotAllowed,
    SealRequired,
    SerialNotOnOrder,
)
from apps.warranty.domain.read_models import ClaimableKinds
from apps.warranty.domain.rules import ClaimKind, ClaimStatus, Outcome
from apps.warranty.models import Claim
from apps.warranty.repositories import ClaimRepository
from apps.warranty.services.contracts import LineRefunds, OrderLines
from core.domain.actor import Actor

CLAIMABLE_STATUSES = frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED})


def _day(moment: datetime | None) -> date | None:
    return timezone.localtime(moment).date() if moment is not None else None


def _note(text: str) -> str:
    return text.strip()[:2000]


class ClaimService:
    def __init__(
        self,
        claims: ClaimRepository,
        lines: OrderLines,
        refunds: LineRefunds,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._claims = claims
        self._lines = lines
        self._refunds = refunds
        self._clock = clock

    # for the claim form: what each line of the client's order can still be claimed for
    def claimable(self, actor: Actor, order_id: int) -> list[ClaimableKinds]:
        lines = self._lines.of_order(order_id)
        if not lines or not (actor.is_staff or lines[0].client_id == actor.user_id):
            raise LineNotClaimable
        today = timezone.localdate(self._clock())
        return [self._kinds(line, today) for line in lines]

    def submit(self, actor: Actor, command: SubmitClaim) -> Claim:
        line = self._lines.line(command.order_id, command.item_id)
        if (
            line is None
            or line.client_id != actor.user_id
            or line.status not in CLAIMABLE_STATUSES
            or line.returned_quantity >= line.quantity
        ):
            raise LineNotClaimable
        if self._claims.open_for_item(line.item_id) is not None:
            raise ClaimAlreadyOpen
        serial = serials.normalize(command.serial)
        if line.serials and serial not in line.serials:
            raise SerialNotOnOrder(errors={"serial": [SerialNotOnOrder.default_detail]})
        now = self._clock()
        protection = rules.protection_for(
            command.kind,
            ordered_on=timezone.localtime(line.ordered_at).date(),
            delivered_on=_day(line.delivered_at),
            today=timezone.localdate(now),
            extension_days=self._claims.repair_extension_days(line.item_id),
        )
        if protection is None:
            raise ClaimWindowClosed
        return self._claims.create(
            order_id=line.order_id,
            item_id=line.item_id,
            client_id=actor.user_id,
            serial=serial,
            kind=command.kind.value,
            protection=protection.value,
            description=_note(command.description),
            photos=list(command.photos)[:6],
            answer_due=now + timedelta(hours=rules.ANSWER_HOURS),
        )

    def answer(self, actor: Actor, claim: Claim, command: AnswerClaim) -> Claim:
        self._expect(claim, ClaimStatus.SUBMITTED)
        claim.return_method = command.return_method.value
        claim.answer_note = _note(command.note)
        claim.answered_at = self._clock()
        return self._move(
            claim, actor, ClaimStatus.ANSWERED, ("return_method", "answer_note", "answered_at")
        )

    # the product is in: the drop-off slip is the claim number and the reception date. A client
    # may also walk in before any answer.
    def receive(self, actor: Actor, claim: Claim, command: ReceiveClaim) -> Claim:
        self._expect(claim, ClaimStatus.SUBMITTED, ClaimStatus.ANSWERED)
        now = self._clock()
        claim.received_at = now
        claim.sealed = command.sealed
        claim.diagnosis_due = rules.add_working_days(now, rules.DIAGNOSIS_WORKING_DAYS)
        if command.note.strip():
            claim.answer_note = "\n".join(filter(None, (claim.answer_note, _note(command.note))))
        return self._move(
            claim,
            actor,
            ClaimStatus.RECEIVED,
            ("received_at", "sealed", "diagnosis_due", "answer_note"),
        )

    def diagnose(self, actor: Actor, claim: Claim, command: DiagnoseClaim) -> Claim:
        self._expect(claim, ClaimStatus.RECEIVED)
        kind = ClaimKind(claim.kind)
        if command.outcome not in rules.outcomes_for(kind, covered=command.covered):
            raise OutcomeNotAllowed
        line = self._line_of(claim)
        if (
            kind is ClaimKind.CHANGE_OF_MIND
            and command.covered
            and line.sealed_return_only
            and claim.sealed is not True
        ):
            raise SealRequired
        now = self._clock()
        claim.covered = command.covered
        claim.outcome = command.outcome.value
        claim.diagnosis_note = _note(command.note)
        claim.diagnosed_at = now
        claim.handled_by_id = actor.user_id
        fields = ["covered", "outcome", "diagnosis_note", "diagnosed_at", "handled_by"]
        if command.outcome is Outcome.REPAIR:
            claim.outcome_due = rules.add_working_days(now, rules.REPAIR_WORKING_DAYS)
            return self._move(claim, actor, ClaimStatus.REPAIRING, (*fields, "outcome_due"))
        if command.outcome is Outcome.REFUND:
            # the money goes back within 15 days, recorded as the order's refund due
            claim.outcome_due = now + timedelta(days=rules.REFUND_DAYS)
            fields.append("outcome_due")
            self._refunds.refund_unit(
                actor, claim.order_id, claim.item_id, reason=f"Réclamation {claim.number}"
            )
        elif command.outcome is Outcome.EXCHANGE:
            claim.new_serial = self._new_serial(command.new_serial)
            claim.exchange_warranty_until = rules.exchange_warranty_until(
                self._warranty_until(line, claim.item_id), timezone.localdate(now)
            )
            fields += ["new_serial", "exchange_warranty_until"]
        else:
            claim.quote = command.quote
            fields.append("quote")
        claim.closed_at = now
        return self._move(claim, actor, ClaimStatus.CLOSED, (*fields, "closed_at"))

    # the warranty is extended by the time the product spent in repair (warranty policy)
    def finish_repair(self, actor: Actor, claim: Claim, command: FinishRepair) -> Claim:
        self._expect(claim, ClaimStatus.REPAIRING)
        now = self._clock()
        claim.repaired_at = now
        claim.closed_at = now
        if command.note.strip():
            claim.diagnosis_note = "\n".join(
                filter(None, (claim.diagnosis_note, _note(command.note)))
            )
        return self._move(
            claim, actor, ClaimStatus.CLOSED, ("repaired_at", "closed_at", "diagnosis_note")
        )

    def _kinds(self, line: ClaimableLine, today: date) -> ClaimableKinds:
        ordered_on = timezone.localtime(line.ordered_at).date()
        delivered_on = _day(line.delivered_at)
        extension = self._claims.repair_extension_days(line.item_id)
        open_claim = self._claims.open_for_item(line.item_id)
        claimable = line.status in CLAIMABLE_STATUSES and line.returned_quantity < line.quantity
        kinds = tuple(
            kind
            for kind in ClaimKind
            if claimable
            and open_claim is None
            and rules.protection_for(
                kind,
                ordered_on=ordered_on,
                delivered_on=delivered_on,
                today=today,
                extension_days=extension,
            )
            is not None
        )
        return ClaimableKinds(
            order_id=line.order_id,
            item_id=line.item_id,
            name=line.name,
            serials=line.serials,
            kinds=kinds,
            trial_until=delivered_on + timedelta(days=rules.TRIAL_DAYS) if delivered_on else None,
            warranty_until=self._warranty_until(line, line.item_id) if delivered_on else None,
            authenticity_until=rules.add_months(ordered_on, rules.AUTHENTICITY_MONTHS),
            open_claim_id=open_claim.pk if open_claim is not None else None,
        )

    def _warranty_until(self, line: ClaimableLine, item_id: int) -> date:
        delivered_on = _day(line.delivered_at) or timezone.localtime(line.ordered_at).date()
        return rules.add_months(delivered_on, rules.WARRANTY_MONTHS) + timedelta(
            days=self._claims.repair_extension_days(item_id)
        )

    def _line_of(self, claim: Claim) -> ClaimableLine:
        line = self._lines.line(claim.order_id, claim.item_id)
        if line is None:
            raise LineNotClaimable
        return line

    @staticmethod
    def _new_serial(raw: str) -> str:
        serial = serials.normalize(raw)
        if serial and (why := serials.problem(serial)) is not None:
            raise OutcomeNotAllowed(why)
        return serial

    @staticmethod
    def _expect(claim: Claim, *statuses: ClaimStatus) -> None:
        if ClaimStatus(claim.status) not in statuses:
            raise ClaimStepNotAllowed

    def _move(
        self, claim: Claim, actor: Actor, status: ClaimStatus, fields: tuple[str, ...]
    ) -> Claim:
        claim.status = status.value
        if actor.is_staff and "handled_by" not in fields:
            claim.handled_by_id = actor.user_id
            fields = (*fields, "handled_by")
        self._claims.save(claim, fields=(*fields, "status"))
        return claim
