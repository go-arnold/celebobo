from collections.abc import Callable
from datetime import datetime

from django.db.models import QuerySet

from apps.warranty.domain.errors import ClaimNotFound
from apps.warranty.domain.read_models import ClaimView
from apps.warranty.domain.rules import ClaimKind, ClaimStatus, Outcome, Protection, ReturnMethod
from apps.warranty.models import Claim
from core.domain.actor import Actor


# the client's own claims (`own`, also for staff in their shop account), or every claim for staff
def _scoped(actor: Actor, *, own: bool) -> QuerySet[Claim]:
    claims = Claim.objects.select_related("order", "item", "client")
    return claims if actor.is_staff and not own else claims.filter(client_id=actor.user_id)


class ClaimSelector:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def page(
        self, actor: Actor, *, own: bool, status: ClaimStatus | None, offset: int, limit: int
    ) -> tuple[list[ClaimView], int]:
        claims = _scoped(actor, own=own)
        if status is not None:
            claims = claims.filter(status=status.value)
        now = self._clock()
        return [_view(claim, now) for claim in claims[offset : offset + limit]], claims.count()

    def one(self, actor: Actor, claim_id: int, *, own: bool = False) -> ClaimView:
        claim = _scoped(actor, own=own).filter(pk=claim_id).first()
        if claim is None:
            raise ClaimNotFound
        return _view(claim, self._clock())


def overdue(claim: Claim, now: datetime) -> bool:
    status = ClaimStatus(claim.status)
    due = {
        ClaimStatus.SUBMITTED: claim.answer_due,
        ClaimStatus.RECEIVED: claim.diagnosis_due,
        ClaimStatus.REPAIRING: claim.outcome_due,
    }.get(status)
    return due is not None and now > due


def _name(claim: Claim) -> str:
    client = claim.client
    return " ".join(filter(None, (client.first_name, client.last_name))) or client.email


def _view(claim: Claim, now: datetime) -> ClaimView:
    return ClaimView(
        id=claim.pk,
        number=claim.number,
        order_id=claim.order_id,
        order_number=claim.order.number,
        item_id=claim.item_id,
        product_name=claim.item.product_name,
        serial=claim.serial,
        client_id=claim.client_id,
        client_name=_name(claim),
        kind=ClaimKind(claim.kind),
        protection=Protection(claim.protection),
        description=claim.description,
        photos=tuple(claim.photos or ()),
        status=ClaimStatus(claim.status),
        created_at=claim.created_at,
        answer_due=claim.answer_due,
        return_method=ReturnMethod(claim.return_method) if claim.return_method else None,
        answer_note=claim.answer_note,
        answered_at=claim.answered_at,
        received_at=claim.received_at,
        sealed=claim.sealed,
        diagnosis_due=claim.diagnosis_due,
        covered=claim.covered,
        outcome=Outcome(claim.outcome) if claim.outcome else None,
        diagnosis_note=claim.diagnosis_note,
        diagnosed_at=claim.diagnosed_at,
        outcome_due=claim.outcome_due,
        new_serial=claim.new_serial,
        quote=claim.quote,
        exchange_warranty_until=claim.exchange_warranty_until,
        repaired_at=claim.repaired_at,
        closed_at=claim.closed_at,
        overdue=overdue(claim, now),
    )
