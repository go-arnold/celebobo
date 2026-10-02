from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.analytics.domain.periods import Granularity


@dataclass(frozen=True, slots=True, kw_only=True)
class Totals:
    revenue: Decimal
    profit: Decimal
    costed_revenue: Decimal
    sales_count: int
    units: int

    @property
    def average_basket(self) -> Decimal:
        return _ratio(self.revenue, self.sales_count)

    @property
    def margin_rate(self) -> Decimal | None:
        if not self.costed_revenue:
            return None
        return (self.profit / self.costed_revenue * 100).quantize(Decimal("0.1"))


@dataclass(frozen=True, slots=True, kw_only=True)
class Metric:
    value: Decimal
    previous: Decimal
    change: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Summary:
    start: datetime
    end: datetime
    revenue: Metric
    profit: Metric
    sales_count: Metric
    units: Metric
    average_basket: Metric
    margin_rate: Decimal | None
    today_revenue: Decimal
    open_orders: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SeriesPoint:
    bucket: date
    revenue: Decimal
    profit: Decimal
    sales_count: int
    average_basket: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class Series:
    granularity: Granularity
    points: list[SeriesPoint]


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentShare:
    payment_method: str
    revenue: Decimal
    sales_count: int
    share: float


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryPerformance:
    category_id: int
    name: str
    revenue: Decimal
    profit: Decimal
    units: int
    margin_rate: Decimal | None
    share: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPerformance:
    product_id: int
    name: str
    image: str
    revenue: Decimal
    profit: Decimal
    units: int


@dataclass(frozen=True, slots=True, kw_only=True)
class HeatCell:
    weekday: int
    hour: int
    sales_count: int
    revenue: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class SellerRanking:
    seller_id: int
    name: str
    revenue: Decimal
    profit: Decimal
    sales_count: int
    units: int
    share: float


@dataclass(frozen=True, slots=True, kw_only=True)
class SlowMover:
    product_id: int
    name: str
    image: str
    stock: int
    last_sold_at: datetime | None


def _ratio(amount: Decimal, count: int) -> Decimal:
    return (amount / count).quantize(Decimal("0.01")) if count else Decimal("0.00")
