from dataclasses import dataclass
from decimal import Decimal

from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipTerms:
    enabled: bool
    monthly_price: Decimal
    yearly_price: Decimal
    trial_days: int
    reminder_days: int


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
    membership: MembershipTerms
    points: PointsTerms
    app_links: AppLinks


@dataclass(frozen=True, slots=True, kw_only=True)
class LoyaltySettingsChanges:
    membership_enabled: Maybe[bool] = UNSET
    membership_monthly_price: Maybe[Decimal] = UNSET
    membership_yearly_price: Maybe[Decimal] = UNSET
    membership_trial_days: Maybe[int] = UNSET
    membership_reminder_days: Maybe[int] = UNSET
    points_enabled: Maybe[bool] = UNSET
    points_percent: Maybe[Decimal] = UNSET
    points_validity_months: Maybe[int] = UNSET
    app_store_url: Maybe[str] = UNSET
    play_store_url: Maybe[str] = UNSET
