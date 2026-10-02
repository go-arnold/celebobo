from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from apps.analytics.domain.periods import Window, change_rate, window_for
from apps.analytics.domain.queries import AnalyticsFilters, FactScope
from apps.analytics.domain.read_models import (
    CategoryPerformance,
    HeatCell,
    Metric,
    PaymentShare,
    ProductPerformance,
    SellerRanking,
    Series,
    SeriesPoint,
    SlowMover,
    Summary,
    Totals,
)
from apps.analytics.selectors import FactSelector
from apps.analytics.services.contracts import CatalogLabels, OrderPipeline, SellerNames
from core.domain.actor import Actor

EMPTY = Totals(
    revenue=Decimal("0.00"),
    profit=Decimal("0.00"),
    costed_revenue=Decimal("0.00"),
    sales_count=0,
    units=0,
)


class InsightService:
    def __init__(
        self,
        facts: FactSelector,
        labels: CatalogLabels,
        sellers: SellerNames,
        pipeline: OrderPipeline,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._facts = facts
        self._labels = labels
        self._sellers = sellers
        self._pipeline = pipeline
        self._clock = clock

    def summary(self, actor: Actor, filters: AnalyticsFilters) -> Summary:
        window, scope = self._resolve(actor, filters)
        current = self._facts.totals(window, scope)
        previous = self._facts.totals(window.previous(), scope)
        today = window_for(self._now(), date_from=self._now().date())
        _, open_orders = self._pipeline.open_orders(actor, limit=0)
        return Summary(
            start=window.start,
            end=window.end,
            revenue=_metric(current.revenue, previous.revenue),
            profit=_metric(current.profit, previous.profit),
            sales_count=_metric(Decimal(current.sales_count), Decimal(previous.sales_count)),
            units=_metric(Decimal(current.units), Decimal(previous.units)),
            average_basket=_metric(current.average_basket, previous.average_basket),
            margin_rate=current.margin_rate,
            today_revenue=self._facts.totals(today, scope).revenue,
            open_orders=open_orders,
        )

    def series(self, actor: Actor, filters: AnalyticsFilters) -> Series:
        window, scope = self._resolve(actor, filters)
        rows = self._facts.series(window, scope)
        return Series(
            granularity=window.granularity,
            points=[
                SeriesPoint(
                    bucket=bucket,
                    revenue=rows.get(bucket, EMPTY).revenue,
                    profit=rows.get(bucket, EMPTY).profit,
                    sales_count=rows.get(bucket, EMPTY).sales_count,
                    average_basket=rows.get(bucket, EMPTY).average_basket,
                )
                for bucket in window.buckets()
            ],
        )

    def payment_split(self, actor: Actor, filters: AnalyticsFilters) -> list[PaymentShare]:
        window, scope = self._resolve(actor, filters)
        rows = self._facts.grouped(window, scope, "payment_method")
        total = sum((row.revenue for row in rows.values()), Decimal(0))
        return sorted(
            (
                PaymentShare(
                    payment_method=method,
                    revenue=row.revenue,
                    sales_count=row.sales_count,
                    share=_share(row.revenue, total),
                )
                for method, row in rows.items()
            ),
            key=lambda item: (-item.revenue, item.payment_method),
        )

    def categories(self, actor: Actor, filters: AnalyticsFilters) -> list[CategoryPerformance]:
        window, scope = self._resolve(actor, filters)
        rows = self._facts.grouped(window, scope, "category_id")
        names = self._labels.categories(list(rows))
        total = sum((row.revenue for row in rows.values()), Decimal(0))
        return sorted(
            (
                CategoryPerformance(
                    category_id=category_id,
                    name=names.get(category_id, ""),
                    revenue=row.revenue,
                    profit=row.profit,
                    units=row.units,
                    margin_rate=row.margin_rate,
                    share=_share(row.revenue, total),
                )
                for category_id, row in rows.items()
            ),
            key=lambda item: (-item.revenue, item.category_id),
        )

    def top_products(
        self, actor: Actor, filters: AnalyticsFilters, *, by: str, limit: int
    ) -> list[ProductPerformance]:
        window, scope = self._resolve(actor, filters)
        ranked = self._facts.ranked(window, scope, "product_id", by=by, limit=limit)
        labels = self._labels.products([product_id for product_id, _ in ranked])
        return [
            ProductPerformance(
                product_id=product_id,
                name=labels[product_id].name if product_id in labels else "",
                image=labels[product_id].image if product_id in labels else "",
                revenue=row.revenue,
                profit=row.profit,
                units=row.units,
            )
            for product_id, row in ranked
        ]

    def heatmap(self, actor: Actor, filters: AnalyticsFilters) -> list[HeatCell]:
        window, scope = self._resolve(actor, filters)
        return self._facts.heatmap(window, scope)

    def sellers(self, actor: Actor, filters: AnalyticsFilters) -> list[SellerRanking]:
        window, scope = self._resolve(actor, filters)
        rows = self._facts.grouped(window, scope, "seller_id")
        names = self._sellers.names(list(rows))
        total = sum((row.revenue for row in rows.values()), Decimal(0))
        return sorted(
            (
                SellerRanking(
                    seller_id=seller_id,
                    name=names.get(seller_id, ""),
                    revenue=row.revenue,
                    profit=row.profit,
                    sales_count=row.sales_count,
                    units=row.units,
                    share=_share(row.revenue, total),
                )
                for seller_id, row in rows.items()
            ),
            key=lambda item: (-item.revenue, item.seller_id),
        )

    def slow_movers(
        self, actor: Actor, filters: AnalyticsFilters, *, limit: int
    ) -> list[SlowMover]:
        window, scope = self._resolve(actor, filters)
        sold = self._facts.sold_product_ids(window, scope)
        candidates = [
            product
            for product in self._labels.stocked(limit=limit * 5)
            if product.id not in sold and product.created_at < window.start
        ][:limit]
        last_sold = self._facts.last_sold(product.id for product in candidates)
        return [
            SlowMover(
                product_id=product.id,
                name=product.name,
                image=product.image,
                stock=product.stock,
                last_sold_at=last_sold.get(product.id),
            )
            for product in candidates
        ]

    def _resolve(self, actor: Actor, filters: AnalyticsFilters) -> tuple[Window, FactScope]:
        window = window_for(
            self._now(),
            period=filters.period,
            date_from=filters.date_from,
            date_to=filters.date_to,
        )
        return window, FactScope(
            seller_id=filters.seller_id if actor.is_staff else actor.user_id,
            category_id=filters.category_id,
            payment_method=filters.payment_method,
        )

    def _now(self) -> datetime:
        return timezone.localtime(self._clock())


def _metric(current: Decimal, previous: Decimal) -> Metric:
    return Metric(value=current, previous=previous, change=change_rate(current, previous))


def _share(amount: Decimal, total: Decimal) -> float:
    return round(float(amount / total * 100), 1) if total else 0.0
