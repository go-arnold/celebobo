from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.analytics.api.v1.serializers import (
    AnalyticsFiltersInput,
    CategoryPerformanceOutput,
    HeatCellOutput,
    OpenOrderOutput,
    PaymentShareOutput,
    ProductPerformanceOutput,
    RankingInput,
    RecentSaleOutput,
    SellerRankingOutput,
    SeriesOutput,
    SlowMoverOutput,
    SummaryOutput,
)
from apps.analytics.domain.queries import AnalyticsFilters
from apps.analytics.facades import AnalyticsFacade
from apps.analytics.permissions import ANALYTICS_VIEW, DASHBOARD_VIEW
from core.api.views import UseCaseViewSet
from core.container import Inject

FILTERS = [AnalyticsFiltersInput]


class InsightViewSet(UseCaseViewSet):
    analytics = Inject(AnalyticsFacade)

    def filters(self) -> AnalyticsFilters:
        return self.parse(
            AnalyticsFiltersInput, into=AnalyticsFilters, data=self.request.query_params
        )


class DashboardViewSet(InsightViewSet):
    action_permissions = dict.fromkeys(
        ("summary", "series", "payment_split", "top_products", "recent_sales", "open_orders"),
        (DASHBOARD_VIEW,),
    )

    @extend_schema(parameters=FILTERS, responses=SummaryOutput)
    def summary(self, request: Request) -> Response:
        return self.respond(SummaryOutput, self.analytics.summary(self.actor, self.filters()))

    @extend_schema(parameters=FILTERS, responses=SeriesOutput)
    def series(self, request: Request) -> Response:
        return self.respond(SeriesOutput, self.analytics.series(self.actor, self.filters()))

    @extend_schema(parameters=FILTERS, responses=PaymentShareOutput(many=True))
    def payment_split(self, request: Request) -> Response:
        shares = self.analytics.payment_split(self.actor, self.filters())
        return self.respond(PaymentShareOutput, shares, many=True)

    @extend_schema(
        parameters=[*FILTERS, RankingInput], responses=ProductPerformanceOutput(many=True)
    )
    def top_products(self, request: Request) -> Response:
        ranking = self.validated(RankingInput, data=request.query_params)
        products = self.analytics.top_products(
            self.actor, self.filters(), by=ranking["by"], limit=ranking.get("limit")
        )
        return self.respond(ProductPerformanceOutput, products, many=True)

    @extend_schema(responses=RecentSaleOutput(many=True))
    def recent_sales(self, request: Request) -> Response:
        return self.respond(RecentSaleOutput, self.analytics.recent_sales(self.actor), many=True)

    @extend_schema(responses=OpenOrderOutput(many=True))
    def open_orders(self, request: Request) -> Response:
        orders, total = self.analytics.open_orders(self.actor)
        return Response({"count": total, "results": OpenOrderOutput(orders, many=True).data})


class AnalyticsViewSet(InsightViewSet):
    action_permissions = dict.fromkeys(
        ("categories", "peak_hours", "sellers", "slow_movers"), (ANALYTICS_VIEW,)
    )

    @extend_schema(parameters=FILTERS, responses=CategoryPerformanceOutput(many=True))
    def categories(self, request: Request) -> Response:
        rows = self.analytics.categories(self.actor, self.filters())
        return self.respond(CategoryPerformanceOutput, rows, many=True)

    @extend_schema(parameters=FILTERS, responses=HeatCellOutput(many=True))
    def peak_hours(self, request: Request) -> Response:
        return self.respond(
            HeatCellOutput, self.analytics.heatmap(self.actor, self.filters()), many=True
        )

    @extend_schema(parameters=FILTERS, responses=SellerRankingOutput(many=True))
    def sellers(self, request: Request) -> Response:
        rows = self.analytics.sellers(self.actor, self.filters())
        return self.respond(SellerRankingOutput, rows, many=True)

    @extend_schema(parameters=FILTERS, responses=SlowMoverOutput(many=True))
    def slow_movers(self, request: Request) -> Response:
        rows = self.analytics.slow_movers(self.actor, self.filters())
        return self.respond(SlowMoverOutput, rows, many=True)
