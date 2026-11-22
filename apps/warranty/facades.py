from django.db import transaction

from apps.warranty.domain.commands import (
    AnswerClaim,
    DiagnoseClaim,
    FinishRepair,
    ReceiveClaim,
    SubmitClaim,
)
from apps.warranty.domain.errors import ClaimNotFound
from apps.warranty.domain.events import ClaimSubmitted, ClaimUpdated
from apps.warranty.domain.read_models import ClaimableKinds, ClaimView
from apps.warranty.domain.rules import ClaimStatus, Outcome, ReturnMethod, client_message
from apps.warranty.models import Claim
from apps.warranty.repositories import ClaimRepository
from apps.warranty.selectors import ClaimSelector
from apps.warranty.services.claims import ClaimService
from core.domain.actor import Actor
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class ClaimFacade:
    def __init__(
        self,
        *,
        claims: ClaimService,
        repository: ClaimRepository,
        selector: ClaimSelector,
        publisher: EventPublisher,
    ) -> None:
        self._claims = claims
        self._repository = repository
        self._selector = selector
        self._publisher = publisher

    def claimable(self, actor: Actor, order_id: int) -> list[ClaimableKinds]:
        return self._claims.claimable(actor, order_id)

    def submit(self, actor: Actor, command: SubmitClaim) -> ClaimView:
        with transaction.atomic():
            claim = self._claims.submit(actor, command)
            view = self._selector.one(actor, claim.pk, own=True)
            self._publisher.publish(
                ClaimSubmitted(
                    claim_id=claim.pk,
                    client_id=claim.client_id,
                    order_id=claim.order_id,
                    number=view.number,
                    product=view.product_name,
                    client_name=view.client_name,
                    kind_label=view.kind.label,
                    actor_id=actor.user_id,
                )
            )
        return view

    def page(
        self, actor: Actor, *, own: bool, status: ClaimStatus | None, offset: int, limit: int
    ) -> tuple[list[ClaimView], int]:
        return self._selector.page(actor, own=own, status=status, offset=offset, limit=limit)

    def detail(self, actor: Actor, claim_id: int, *, own: bool = False) -> ClaimView:
        return self._selector.one(actor, claim_id, own=own)

    def answer(self, actor: Actor, claim_id: int, command: AnswerClaim) -> ClaimView:
        return self._step(actor, claim_id, lambda claim: self._claims.answer(actor, claim, command))

    def receive(self, actor: Actor, claim_id: int, command: ReceiveClaim) -> ClaimView:
        return self._step(
            actor, claim_id, lambda claim: self._claims.receive(actor, claim, command)
        )

    def diagnose(self, actor: Actor, claim_id: int, command: DiagnoseClaim) -> ClaimView:
        return self._step(
            actor, claim_id, lambda claim: self._claims.diagnose(actor, claim, command)
        )

    def finish_repair(self, actor: Actor, claim_id: int, command: FinishRepair) -> ClaimView:
        return self._step(
            actor, claim_id, lambda claim: self._claims.finish_repair(actor, claim, command)
        )

    def _step(self, actor: Actor, claim_id: int, apply) -> ClaimView:  # type: ignore[no-untyped-def]
        with transaction.atomic():
            claim: Claim | None = self._repository.get(claim_id, for_update=True)
            if claim is None:
                raise ClaimNotFound
            claim = apply(claim)
            status = ClaimStatus(claim.status)
            outcome = Outcome(claim.outcome) if claim.outcome else None
            self._publisher.publish(
                ClaimUpdated(
                    claim_id=claim.pk,
                    client_id=claim.client_id,
                    status=claim.status,
                    outcome=claim.outcome or None,
                    number=claim.number,
                    message=client_message(
                        status,
                        outcome,
                        number=claim.number,
                        return_method=ReturnMethod(claim.return_method)
                        if claim.return_method
                        else None,
                        quote=str(claim.quote) if claim.quote is not None else None,
                    ),
                    actor_id=actor.user_id,
                )
            )
        return self._selector.one(actor, claim_id)
