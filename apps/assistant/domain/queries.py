from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.assistant.domain.enums import Sentiment


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductQuery:
    query: str
    category: str | None = None
    on_sale: bool | None = None
    max_price: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LogFilters:
    sentiment: Sentiment | None = None
    topic: str | None = None
    search: str | None = None
    date_from: date | None = None
    date_to: date | None = None
