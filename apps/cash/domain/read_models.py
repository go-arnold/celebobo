from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.cash.domain.rules import Level


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectionView:
    order_id: int
    order_number: str
    amount: Decimal
    left: Decimal
    collected_at: datetime
    due_at: datetime
    overdue: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RemittanceView:
    amount: Decimal
    reference: str
    received_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CashSummary:
    reseller_id: int
    reseller_name: str
    level: Level
    cap: Decimal
    held: Decimal
    overdue: Decimal
    oldest_due: datetime | None
    # why new orders are refused, if they are
    blocked_reason: str | None
    collections: tuple[CollectionView, ...] = ()
    remittances: tuple[RemittanceView, ...] = ()
