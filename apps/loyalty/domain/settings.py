from dataclasses import dataclass
from decimal import Decimal

from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class PointsTerms:
    enabled: bool
    percent: Decimal
    validity_months: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AppLinks:
    app_store: str
    play_store: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Programmes:
    points: PointsTerms
    app_links: AppLinks


@dataclass(frozen=True, slots=True, kw_only=True)
class LoyaltySettingsChanges:
    points_enabled: Maybe[bool] = UNSET
    points_percent: Maybe[Decimal] = UNSET
    points_validity_months: Maybe[int] = UNSET
    app_store_url: Maybe[str] = UNSET
    play_store_url: Maybe[str] = UNSET
