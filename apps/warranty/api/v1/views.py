from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.warranty.api.v1.serializers import (
    AnswerClaimInput,
    ClaimableLineOutput,
    ClaimFiltersInput,
    ClaimOutput,
    DiagnoseClaimInput,
    FinishRepairInput,
    ReceiveClaimInput,
    SubmitClaimInput,
)
from apps.warranty.domain.commands import (
    AnswerClaim,
    DiagnoseClaim,
    FinishRepair,
    ReceiveClaim,
    SubmitClaim,
)
from apps.warranty.domain.rules import ClaimStatus
from apps.warranty.facades import ClaimFacade
from apps.warranty.permissions import CLAIMS_MANAGE, CLAIMS_SUBMIT_OWN
from core.api.idempotency import idempotent
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class ClientClaimViewSet(UseCaseViewSet):
    """The client's claims: what an order can be claimed for, submit, follow."""

    action_permissions = {
        "claimable": (CLAIMS_SUBMIT_OWN,),
        "list": (CLAIMS_SUBMIT_OWN,),
        "retrieve": (CLAIMS_SUBMIT_OWN,),
        "create": (CLAIMS_SUBMIT_OWN,),
    }
    claims = Inject(ClaimFacade)

    @extend_schema(responses=ClaimableLineOutput(many=True))
    def claimable(self, request: Request, order_id: int) -> Response:
        return self.respond(
            ClaimableLineOutput, self.claims.claimable(self.actor, order_id), many=True
        )

    @extend_schema(responses=page_of(ClaimOutput))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        claims, total = self.claims.page(
            self.actor, own=True, status=None, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=ClaimOutput(claims, many=True).data
        )

    @extend_schema(responses=ClaimOutput)
    def retrieve(self, request: Request, claim_id: int) -> Response:
        return self.respond(ClaimOutput, self.claims.detail(self.actor, claim_id, own=True))

    @extend_schema(request=SubmitClaimInput, responses={201: ClaimOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(SubmitClaimInput, into=SubmitClaim)
        return self.respond(ClaimOutput, self.claims.submit(self.actor, command), status=201)


class ClaimViewSet(UseCaseViewSet):
    """Staff handle the claims, step by step."""

    action_permissions = {
        "list": (CLAIMS_MANAGE,),
        "retrieve": (CLAIMS_MANAGE,),
        "answer": (CLAIMS_MANAGE,),
        "receive": (CLAIMS_MANAGE,),
        "diagnose": (CLAIMS_MANAGE,),
        "finish_repair": (CLAIMS_MANAGE,),
    }
    claims = Inject(ClaimFacade)

    @extend_schema(parameters=[ClaimFiltersInput], responses=page_of(ClaimOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(ClaimFiltersInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        status = ClaimStatus(filters["status"]) if filters.get("status") else None
        claims, total = self.claims.page(
            self.actor, own=False, status=status, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=ClaimOutput(claims, many=True).data
        )

    @extend_schema(responses=ClaimOutput)
    def retrieve(self, request: Request, claim_id: int) -> Response:
        return self.respond(ClaimOutput, self.claims.detail(self.actor, claim_id))

    @extend_schema(request=AnswerClaimInput, responses=ClaimOutput)
    def answer(self, request: Request, claim_id: int) -> Response:
        command = self.parse(AnswerClaimInput, into=AnswerClaim)
        return self.respond(ClaimOutput, self.claims.answer(self.actor, claim_id, command))

    @extend_schema(request=ReceiveClaimInput, responses=ClaimOutput)
    def receive(self, request: Request, claim_id: int) -> Response:
        command = self.parse(ReceiveClaimInput, into=ReceiveClaim)
        return self.respond(ClaimOutput, self.claims.receive(self.actor, claim_id, command))

    @extend_schema(request=DiagnoseClaimInput, responses=ClaimOutput)
    @idempotent()
    def diagnose(self, request: Request, claim_id: int) -> Response:
        command = self.parse(DiagnoseClaimInput, into=DiagnoseClaim)
        return self.respond(ClaimOutput, self.claims.diagnose(self.actor, claim_id, command))

    @extend_schema(request=FinishRepairInput, responses=ClaimOutput)
    def finish_repair(self, request: Request, claim_id: int) -> Response:
        command = self.parse(FinishRepairInput, into=FinishRepair)
        return self.respond(ClaimOutput, self.claims.finish_repair(self.actor, claim_id, command))
