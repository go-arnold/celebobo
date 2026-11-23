from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.cagnotte.domain.rules import CampaignKind, Payout, RewardStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class NamedRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignView:
    id: int
    name: str
    description: str
    kind: CampaignKind
    percent: Decimal
    starts_at: datetime
    ends_at: datetime
    min_purchase: Decimal | None
    cap: Decimal | None
    payout: Payout | None
    points_valid_days: int | None
    categories: tuple[NamedRef, ...]
    products: tuple[NamedRef, ...]
    # upcoming, running or ended, at the time of reading
    state: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RewardView:
    id: int
    campaign_id: int
    campaign_name: str
    kind: CampaignKind
    payout: Payout
    order_id: int
    order_number: str
    client_id: int
    client_name: str
    # where staff send a Mobile Money cashback: the order's phone
    phone: str
    amount: Decimal
    # after returns
    kept: Decimal
    # a Mobile Money cashback already sent when the order came back: to deduct from the refund
    owed_back: Decimal
    status: RewardStatus
    available_at: datetime
    paid_at: datetime | None
    reference: str
    created_at: datetime
