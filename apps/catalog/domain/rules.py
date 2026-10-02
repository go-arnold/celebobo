import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.domain.enums import Badge

_CARE_SEPARATORS = re.compile(r"[\n;]+")
_PERCENT = Decimal("0.01")


def current_price(price: Decimal, sale_price: Decimal | None) -> Decimal:
    return sale_price if sale_price is not None and sale_price < price else price


def discount_percent(price: Decimal, sale_price: Decimal | None) -> Decimal | None:
    if sale_price is None or price <= 0 or sale_price >= price:
        return None
    return ((price - sale_price) / price * 100).quantize(_PERCENT, rounding=ROUND_HALF_UP)


def displayed_badge(
    badge: Badge | None, created_at: datetime, *, now: datetime, new_for_days: int
) -> Badge | None:
    if now - created_at <= timedelta(days=new_for_days):
        return Badge.NEW
    return badge


def care_items(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in _CARE_SEPARATORS.split(text) if item.strip())


def rating_distribution(ratings: dict[int, int]) -> dict[int, int]:
    return {stars: ratings.get(stars, 0) for stars in range(5, 0, -1)}
