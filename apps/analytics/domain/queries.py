from dataclasses import dataclass
from datetime import date

from apps.analytics.domain.periods import Period
from apps.orders.domain.enums import PaymentMethod


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalyticsFilters:
    period: Period | None = None
    date_from: date | None = None
    date_to: date | None = None
    category_id: int | None = None
    payment_method: PaymentMethod | None = None
    seller_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FactScope:
    seller_id: int | None = None
    category_id: int | None = None
    payment_method: PaymentMethod | None = None
