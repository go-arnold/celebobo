from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from django.db.models import DecimalField, IntegerField, Max, QuerySet, Sum
from django.db.models.functions import (
    Coalesce,
    ExtractHour,
    ExtractIsoWeekDay,
    TruncDay,
    TruncMonth,
)

from apps.analytics.domain.periods import Granularity, Window
from apps.analytics.domain.queries import FactScope
from apps.analytics.domain.read_models import HeatCell, Totals
from apps.analytics.models import SalesFact

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Decimal("0.00")
TOTALS = {
    "revenue": Coalesce(Sum("revenue"), ZERO, output_field=MONEY),
    "profit": Coalesce(Sum("profit"), ZERO, output_field=MONEY),
    "costed_revenue": Coalesce(Sum("costed_revenue"), ZERO, output_field=MONEY),
    "sales_count": Coalesce(Sum("sales_count"), 0, output_field=IntegerField()),
    "units": Coalesce(Sum("units"), 0, output_field=IntegerField()),
}
ORDERINGS = {"revenue": "-revenue", "units": "-units", "profit": "-profit"}


class FactSelector:
    def totals(self, window: Window, scope: FactScope) -> Totals:
        return _totals(self._facts(window, scope).aggregate(**TOTALS))

    def series(self, window: Window, scope: FactScope) -> dict[date, Totals]:
        trunc = TruncMonth if window.granularity is Granularity.MONTH else TruncDay
        rows = (
            self._facts(window, scope)
            .annotate(period=trunc("bucket"))
            .values("period")
            .annotate(**TOTALS)
        )
        return {row["period"].date(): _totals(row) for row in _rows(rows)}

    def grouped(self, window: Window, scope: FactScope, field: str) -> dict[Any, Totals]:
        rows = self._facts(window, scope).values(field).annotate(**TOTALS)
        return {row[field]: _totals(row) for row in _rows(rows)}

    def ranked(
        self, window: Window, scope: FactScope, field: str, *, by: str, limit: int
    ) -> list[tuple[Any, Totals]]:
        rows = (
            self._facts(window, scope)
            .values(field)
            .annotate(**TOTALS)
            .order_by(ORDERINGS[by], field)[:limit]
        )
        return [(row[field], _totals(row)) for row in _rows(rows)]

    def heatmap(self, window: Window, scope: FactScope) -> list[HeatCell]:
        rows = (
            self._facts(window, scope)
            .annotate(weekday=ExtractIsoWeekDay("bucket"), hour=ExtractHour("bucket"))
            .values("weekday", "hour")
            .annotate(**TOTALS)
            .order_by("weekday", "hour")
        )
        return [
            HeatCell(
                weekday=row["weekday"],
                hour=row["hour"],
                sales_count=row["sales_count"],
                revenue=row["revenue"],
            )
            for row in _rows(rows)
        ]

    def sold_product_ids(self, window: Window, scope: FactScope) -> set[int]:
        facts = self._facts(window, scope).filter(sales_count__gt=0)
        return set(facts.values_list("product_id", flat=True))

    def last_sold(self, product_ids: Iterable[int]) -> dict[int, datetime]:
        rows = (
            SalesFact.objects.filter(product_id__in=list(product_ids), sales_count__gt=0)
            .values("product_id")
            .annotate(last=Max("bucket"))
        )
        return {row["product_id"]: row["last"] for row in _rows(rows)}

    @staticmethod
    def _facts(window: Window, scope: FactScope) -> QuerySet[SalesFact]:
        facts = SalesFact.objects.filter(bucket__gte=window.start, bucket__lt=window.end)
        if scope.seller_id is not None:
            facts = facts.filter(seller_id=scope.seller_id)
        if scope.category_id is not None:
            facts = facts.filter(category_id=scope.category_id)
        if scope.payment_method is not None:
            facts = facts.filter(payment_method=scope.payment_method.value)
        return facts


def _rows(rows: QuerySet[Any, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", list(rows))


def _totals(row: dict[str, Any]) -> Totals:
    return Totals(
        revenue=Decimal(row["revenue"]),
        profit=Decimal(row["profit"]),
        costed_revenue=Decimal(row["costed_revenue"]),
        sales_count=int(row["sales_count"]),
        units=int(row["units"]),
    )
