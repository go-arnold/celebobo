from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from apps.orders.domain.read_models import CampaignOrder


class Catalog(Protocol):
    # each product's category and the category above it
    def categories(self, product_ids: Iterable[int]) -> dict[int, frozenset[int]]: ...

    def known(self, category_ids: Iterable[int], product_ids: Iterable[int]) -> bool: ...


class Orders(Protocol):
    def campaign_order(self, order_id: int) -> CampaignOrder | None: ...


class PointsLedger(Protocol):
    """Cagnotte points live in the loyalty ledger, with their own validity."""

    def enabled(self) -> bool: ...

    def credit(
        self,
        user_id: int,
        order_id: int,
        amount: Decimal,
        *,
        available_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    # ``None``: everything still held
    def reverse(self, order_id: int, amount: Decimal | None = None) -> Decimal: ...


class ReturnPolicy(Protocol):
    def return_days(self) -> int: ...
