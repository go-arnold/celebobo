from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.sales.api.v1.serializers import (
    BulkSalesInput,
    CommissionEntryOutput,
    CommissionSummaryOutput,
    ConvertibleOrderOutput,
    ConvertibleSearchInput,
    ConvertOrderInput,
    EditSaleInput,
    MonthlyCommissionOutput,
    PayoutOutput,
    RecordPayoutInput,
    RecordSaleInput,
    RefundSaleInput,
    ResellerScopeInput,
    SaleDetailOutput,
    SaleFiltersInput,
    SaleOutput,
    SalesStatsOutput,
)
from apps.sales.domain.commands import (
    ConvertOrder,
    EditSale,
    RecordPayout,
    RecordSale,
    RefundSale,
    SaleFilters,
)
from apps.sales.facades import CommissionFacade, SalesFacade
from apps.sales.permissions import (
    COMMISSIONS_PAY,
    COMMISSIONS_VIEW_ALL,
    COMMISSIONS_VIEW_OWN,
    SALES_CONVERT,
    SALES_CREATE,
    SALES_DELETE,
    SALES_EDIT_OWN,
    SALES_REFUND,
    SALES_VIEW_OWN,
)
from core.api.idempotency import idempotent
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class SaleViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (SALES_VIEW_OWN,),
        "retrieve": (SALES_VIEW_OWN,),
        "create": (SALES_CREATE,),
        "bulk": (SALES_CREATE,),
        "partial_update": (SALES_EDIT_OWN,),
        "refund": (SALES_REFUND,),
        "destroy": (SALES_DELETE,),
    }
    sales = Inject(SalesFacade)

    @extend_schema(parameters=[SaleFiltersInput], responses=page_of(SaleOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(SaleFiltersInput, into=SaleFilters, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        result = self.sales.page(self.actor, filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=result.total,
            results=SaleOutput(result.sales, many=True).data,
            meta={"stats": SalesStatsOutput(result.stats).data},
        )

    @extend_schema(responses=SaleDetailOutput)
    def retrieve(self, request: Request, sale_id: int) -> Response:
        return self.respond(SaleDetailOutput, self.sales.detail(self.actor, sale_id))

    @extend_schema(request=RecordSaleInput, responses={201: SaleDetailOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(RecordSaleInput, into=RecordSale)
        return self.respond(SaleDetailOutput, self.sales.record(self.actor, command), status=201)

    @extend_schema(request=BulkSalesInput, responses={201: SaleOutput(many=True)})
    @idempotent()
    def bulk(self, request: Request) -> Response:
        lines = self.validated(BulkSalesInput)["lines"]
        sales = self.sales.record_many(self.actor, lines)
        return self.respond(SaleOutput, sales, many=True, status=201)

    @extend_schema(request=EditSaleInput, responses=SaleDetailOutput)
    def partial_update(self, request: Request, sale_id: int) -> Response:
        changes = self.parse(EditSaleInput, into=EditSale, partial=True)
        return self.respond(SaleDetailOutput, self.sales.edit(self.actor, sale_id, changes))

    @extend_schema(request=RefundSaleInput, responses=SaleDetailOutput)
    @idempotent()
    def refund(self, request: Request, sale_id: int) -> Response:
        command = self.parse(RefundSaleInput, into=RefundSale)
        return self.respond(SaleDetailOutput, self.sales.refund(self.actor, sale_id, command))

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, sale_id: int) -> Response:
        self.sales.delete(self.actor, sale_id)
        return Response(status=204)


class ConversionViewSet(UseCaseViewSet):
    action_permissions = {"list": (SALES_CONVERT,), "create": (SALES_CONVERT,)}
    sales = Inject(SalesFacade)

    @extend_schema(parameters=[ConvertibleSearchInput], responses=ConvertibleOrderOutput(many=True))
    def list(self, request: Request) -> Response:
        search = self.validated(ConvertibleSearchInput, data=request.query_params).get("search")
        orders = self.sales.convertible(self.actor, search or None)
        return self.respond(ConvertibleOrderOutput, orders, many=True)

    @extend_schema(request=ConvertOrderInput, responses={201: SaleDetailOutput(many=True)})
    @idempotent()
    def create(self, request: Request, order_id: int) -> Response:
        command = self.parse(ConvertOrderInput, into=ConvertOrder)
        sales = self.sales.convert(self.actor, order_id, command)
        return self.respond(SaleDetailOutput, sales, many=True, status=201)


class CommissionViewSet(UseCaseViewSet):
    action_permissions = {
        "summary": (COMMISSIONS_VIEW_OWN,),
        "list": (COMMISSIONS_VIEW_OWN,),
        "series": (COMMISSIONS_VIEW_OWN,),
        "overview": (COMMISSIONS_VIEW_ALL,),
    }
    commissions = Inject(CommissionFacade)

    @extend_schema(parameters=[ResellerScopeInput], responses=CommissionSummaryOutput)
    def summary(self, request: Request) -> Response:
        summary = self.commissions.summary(self.actor, self._reseller_id())
        return self.respond(CommissionSummaryOutput, summary)

    @extend_schema(parameters=[ResellerScopeInput], responses=page_of(CommissionEntryOutput))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        entries, total = self.commissions.entries(
            self.actor, self._reseller_id(), offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=CommissionEntryOutput(entries, many=True).data
        )

    @extend_schema(parameters=[ResellerScopeInput], responses=MonthlyCommissionOutput(many=True))
    def series(self, request: Request) -> Response:
        months = self.commissions.monthly(self.actor, self._reseller_id())
        return self.respond(MonthlyCommissionOutput, months, many=True)

    @extend_schema(responses=CommissionSummaryOutput(many=True))
    def overview(self, request: Request) -> Response:
        return self.respond(CommissionSummaryOutput, self.commissions.overview(), many=True)

    def _reseller_id(self) -> int | None:
        scope = self.validated(ResellerScopeInput, data=self.request.query_params)
        reseller_id: int | None = scope.get("reseller_id")
        return reseller_id


class PayoutViewSet(UseCaseViewSet):
    action_permissions = {"list": (COMMISSIONS_VIEW_OWN,), "create": (COMMISSIONS_PAY,)}
    commissions = Inject(CommissionFacade)

    @extend_schema(parameters=[ResellerScopeInput], responses=page_of(PayoutOutput))
    def list(self, request: Request) -> Response:
        scope = self.validated(ResellerScopeInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        payouts, total = self.commissions.payouts(
            self.actor, scope.get("reseller_id"), offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=PayoutOutput(payouts, many=True).data
        )

    @extend_schema(request=RecordPayoutInput, responses={201: PayoutOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(RecordPayoutInput, into=RecordPayout)
        return self.respond(
            PayoutOutput, self.commissions.record_payout(self.actor, command), status=201
        )
