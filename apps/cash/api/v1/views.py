from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cash.api.v1.serializers import (
    CashSummaryOutput,
    RecordRemittanceInput,
    SummaryFiltersInput,
)
from apps.cash.domain.commands import RecordRemittance
from apps.cash.facades import CashFacade
from apps.cash.permissions import CASH_MANAGE, CASH_VIEW_OWN
from core.api.idempotency import idempotent
from core.api.views import UseCaseViewSet
from core.container import Inject


class CashViewSet(UseCaseViewSet):
    """Cash collected by resellers and remitted to Celebobo (reseller policy, section 6)."""

    action_permissions = {
        "summary": (CASH_VIEW_OWN,),
        "overview": (CASH_MANAGE,),
        "remit": (CASH_MANAGE,),
    }
    cash = Inject(CashFacade)

    @extend_schema(parameters=[SummaryFiltersInput], responses=CashSummaryOutput)
    def summary(self, request: Request) -> Response:
        filters = self.validated(SummaryFiltersInput, data=request.query_params)
        return self.respond(
            CashSummaryOutput, self.cash.summary(self.actor, filters.get("reseller_id"))
        )

    @extend_schema(responses=CashSummaryOutput(many=True))
    def overview(self, request: Request) -> Response:
        return self.respond(CashSummaryOutput, self.cash.overview(), many=True)

    @extend_schema(request=RecordRemittanceInput, responses={201: CashSummaryOutput})
    @idempotent()
    def remit(self, request: Request) -> Response:
        command = self.parse(RecordRemittanceInput, into=RecordRemittance)
        return self.respond(CashSummaryOutput, self.cash.remit(self.actor, command), status=201)
