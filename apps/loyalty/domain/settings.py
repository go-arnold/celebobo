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
class CashbackTerms:
    enabled: bool
    members_only: bool
    percent: Decimal
    max_share: int
    min_balance: Decimal
    validity_months: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AppLinks:
    app_store: str
    play_store: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Programmes:
    membership: MembershipTerms
    cashback: CashbackTerms
    app_links: AppLinks


@dataclass(frozen=True, slots=True, kw_only=True)
class LoyaltySettingsChanges:
    membership_enabled: Maybe[bool] = UNSET
    membership_monthly_price: Maybe[Decimal] = UNSET
    membership_yearly_price: Maybe[Decimal] = UNSET
    membership_trial_days: Maybe[int] = UNSET
    membership_reminder_days: Maybe[int] = UNSET
    cashback_enabled: Maybe[bool] = UNSET
    cashback_members_only: Maybe[bool] = UNSET
    cashback_percent: Maybe[Decimal] = UNSET
    cashback_max_share: Maybe[int] = UNSET
    cashback_min_balance: Maybe[Decimal] = UNSET
    cashback_validity_months: Maybe[int] = UNSET
    app_store_url: Maybe[str] = UNSET
    play_store_url: Maybe[str] = UNSET
