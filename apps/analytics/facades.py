from django.core.cache import cache

from apps.analytics.domain.events import SalesFactsRefreshed
from apps.analytics.domain.queries import AnalyticsFilters
from apps.analytics.domain.read_models import (
    CategoryPerformance,
    HeatCell,
    PaymentShare,
    ProductPerformance,
    SellerRanking,
    Series,
    SlowMover,
    Summary,
)
from apps.analytics.repositories import FactsRefresher
from apps.analytics.services.contracts import OrderPipeline, SalesFeed
from apps.analytics.services.insights import InsightService
from apps.orders.domain.read_models import OrderSummary
from apps.sales.domain.read_models import SaleView
from core.domain.actor import Actor
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade

REFRESH_LOCK = "analytics:facts:refresh-scheduled"


@logged_facade
class AnalyticsFacade:
    def __init__(
        self,
        *,
        insights: InsightService,
        feed: SalesFeed,
        pipeline: OrderPipeline,
        top_limit: int,
        widget_limit: int,
        slow_mover_limit: int,
    ) -> None:
        self._insights = insights
        self._feed = feed
        self._pipeline = pipeline
        self._top_limit = top_limit
        self._widget_limit = widget_limit
        self._slow_mover_limit = slow_mover_limit

    def summary(self, actor: Actor, filters: AnalyticsFilters) -> Summary:
        return self._insights.summary(actor, filters)

    def series(self, actor: Actor, filters: AnalyticsFilters) -> Series:
        return self._insights.series(actor, filters)

    def payment_split(self, actor: Actor, filters: AnalyticsFilters) -> list[PaymentShare]:
        return self._insights.payment_split(actor, filters)

    def categories(self, actor: Actor, filters: AnalyticsFilters) -> list[CategoryPerformance]:
        return self._insights.categories(actor, filters)

    def top_products(
        self,
        actor: Actor,
        filters: AnalyticsFilters,
        *,
        by: str = "revenue",
        limit: int | None = None,
    ) -> list[ProductPerformance]:
        return self._insights.top_products(actor, filters, by=by, limit=limit or self._top_limit)

    def heatmap(self, actor: Actor, filters: AnalyticsFilters) -> list[HeatCell]:
        return self._insights.heatmap(actor, filters)

    def sellers(self, actor: Actor, filters: AnalyticsFilters) -> list[SellerRanking]:
        return self._insights.sellers(actor, filters)

    def slow_movers(self, actor: Actor, filters: AnalyticsFilters) -> list[SlowMover]:
        return self._insights.slow_movers(actor, filters, limit=self._slow_mover_limit)

    def recent_sales(self, actor: Actor) -> list[SaleView]:
        return self._feed.recent(actor, limit=self._widget_limit)

    def open_orders(self, actor: Actor) -> tuple[list[OrderSummary], int]:
        return self._pipeline.open_orders(actor, limit=self._widget_limit)


@logged_facade
class FactsFacade:
    def __init__(
        self, *, refresher: FactsRefresher, publisher: EventPublisher, debounce_seconds: int
    ) -> None:
        self._refresher = refresher
        self._publisher = publisher
        self._debounce_seconds = debounce_seconds

    def refresh(self) -> None:
        cache.delete(REFRESH_LOCK)
        self._refresher.refresh()
        self._publisher.publish(SalesFactsRefreshed())

    def claim_refresh(self) -> bool:
        return bool(cache.add(REFRESH_LOCK, 1, timeout=self._debounce_seconds * 4))

    @property
    def debounce_seconds(self) -> int:
        return self._debounce_seconds
