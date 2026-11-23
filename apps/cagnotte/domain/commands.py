from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.cagnotte.domain.rules import CampaignKind, Payout


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignInput:
    name: str
    kind: CampaignKind
    percent: Decimal
    starts_at: datetime
    ends_at: datetime
    # the conditions as announced on the site
    description: str = ""
    min_purchase: Decimal | None = None
    cap: Decimal | None = None
    # cashback only; boosted points are always points
    payout: Payout = Payout.POINTS
    # Cagnotte points stay valid this many days once spendable
    points_valid_days: int = 90
    category_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class PayReward:
    # the Mobile Money transaction
    reference: str
