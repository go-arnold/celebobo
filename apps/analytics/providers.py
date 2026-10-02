from django.utils import timezone

from apps.analytics.adapters.gateways import (
    AccountsSellerNames,
    CatalogProductLabels,
    OrdersPipeline,
    SalesRecentFeed,
)
from apps.analytics.conf import analytics_settings
from apps.analytics.facades import AnalyticsFacade, FactsFacade
from apps.analytics.repositories import FactsRefresher
from apps.analytics.selectors import FactSelector
from apps.analytics.services.contracts import CatalogLabels, OrderPipeline, SalesFeed, SellerNames
from apps.analytics.services.insights import InsightService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(CatalogLabels, lambda _: CatalogProductLabels())
    container.register(SellerNames, lambda _: AccountsSellerNames())
    container.register(OrderPipeline, lambda _: OrdersPipeline())
    container.register(SalesFeed, lambda _: SalesRecentFeed())
    container.register(AnalyticsFacade, _analytics_facade, lifetime=Lifetime.TRANSIENT)
    container.register(FactsFacade, _facts_facade, lifetime=Lifetime.TRANSIENT)


def _analytics_facade(container: Container) -> AnalyticsFacade:
    settings = analytics_settings()
    pipeline = container.resolve(OrderPipeline)
    return AnalyticsFacade(
        insights=InsightService(
            FactSelector(),
            container.resolve(CatalogLabels),
            container.resolve(SellerNames),
            pipeline,
            clock=timezone.now,
        ),
        feed=container.resolve(SalesFeed),
        pipeline=pipeline,
        top_limit=settings.top_limit,
        widget_limit=settings.widget_limit,
        slow_mover_limit=settings.slow_mover_limit,
    )


def _facts_facade(container: Container) -> FactsFacade:
    return FactsFacade(
        refresher=FactsRefresher(),
        publisher=container.resolve(EventPublisher),
        debounce_seconds=analytics_settings().refresh_debounce_seconds,
    )
