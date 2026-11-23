from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.standing.api.v1.serializers import (
    DecideSanctionInput,
    ExplainSanctionInput,
    LevelReviewOutput,
    OpenSanctionInput,
    SanctionFiltersInput,
    SanctionOutput,
    StandingFiltersInput,
    StandingOutput,
)
from apps.standing.domain.commands import DecideSanction, ExplainSanction, OpenSanction
from apps.standing.domain.rules import SanctionStatus
from apps.standing.facades import StandingFacade
from apps.standing.permissions import STANDING_MANAGE, STANDING_VIEW_OWN
from core.api.idempotency import idempotent
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class StandingViewSet(UseCaseViewSet):
    """Reseller levels (reseller policy, section 9)."""

    action_permissions = {"retrieve": (STANDING_VIEW_OWN,), "review": (STANDING_MANAGE,)}
    standing = Inject(StandingFacade)

    @extend_schema(parameters=[StandingFiltersInput], responses=StandingOutput)
    def retrieve(self, request: Request) -> Response:
        filters = self.validated(StandingFiltersInput, data=request.query_params)
        return self.respond(
            StandingOutput, self.standing.standing(self.actor, filters.get("reseller_id"))
        )

    @extend_schema(request=None, responses=LevelReviewOutput)
    def review(self, request: Request) -> Response:
        return Response(LevelReviewOutput({"changed": self.standing.review()}).data)


class SanctionViewSet(UseCaseViewSet):
    """Sanctions (reseller policy, section 10)."""

    action_permissions = {
        "list": (STANDING_MANAGE,),
        "create": (STANDING_MANAGE,),
        "explain": (STANDING_VIEW_OWN,),
        "decide": (STANDING_MANAGE,),
    }
    standing = Inject(StandingFacade)

    @extend_schema(parameters=[SanctionFiltersInput], responses=page_of(SanctionOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(SanctionFiltersInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        status = SanctionStatus(filters["status"]) if filters.get("status") else None
        rows, total = self.standing.sanctions(
            reseller_id=filters.get("reseller_id"),
            status=status,
            offset=page.offset,
            limit=page.page_size,
        )
        return page_response(
            request, page, total=total, results=SanctionOutput(rows, many=True).data
        )

    @extend_schema(request=OpenSanctionInput, responses={201: SanctionOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(OpenSanctionInput, into=OpenSanction)
        return self.respond(SanctionOutput, self.standing.open(self.actor, command), status=201)

    @extend_schema(request=ExplainSanctionInput, responses=SanctionOutput)
    def explain(self, request: Request, sanction_id: int) -> Response:
        command = self.parse(ExplainSanctionInput, into=ExplainSanction)
        return self.respond(SanctionOutput, self.standing.explain(self.actor, sanction_id, command))

    @extend_schema(request=DecideSanctionInput, responses=SanctionOutput)
    def decide(self, request: Request, sanction_id: int) -> Response:
        command = self.parse(DecideSanctionInput, into=DecideSanction)
        return self.respond(SanctionOutput, self.standing.decide(self.actor, sanction_id, command))
