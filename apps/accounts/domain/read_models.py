from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.accounts.domain.enums import AddressLabel, Availability
from core.domain.actor import Role


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerProfile:
    referral_code: str | None
    availability: Availability
    commission_rate: Decimal
    invited_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Profile:
    id: int
    email: str
    first_name: str
    last_name: str
    phone_number: str | None
    avatar: str
    role: Role
    email_verified: bool
    date_joined: datetime
    invited_by_code: str | None
    permissions: tuple[str, ...]
    reseller: ResellerProfile | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AddressView:
    id: int
    label: AddressLabel
    recipient: str
    phone: str
    line1: str
    quarter: str
    city: str
    country: str
    is_default: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralCheck:
    valid: bool
    reseller_first_name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class WsTicket:
    ticket: str
    expires_in: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerRef:
    id: int
    name: str
    email: str
    availability: Availability


@dataclass(frozen=True, slots=True, kw_only=True)
class Contact:
    id: int
    email: str
    first_name: str
    role: Role


@dataclass(frozen=True, slots=True, kw_only=True)
class SellerProfile:
    id: int
    name: str
    role: Role
    commission_rate: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ManagerRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerAccount:
    id: int
    first_name: str
    last_name: str
    name: str
    email: str
    phone_number: str | None
    avatar: str
    referral_code: str | None
    commission_rate: Decimal
    availability: Availability
    is_active: bool
    manager: ManagerRef | None
    date_joined: datetime
    last_seen_at: datetime | None
    invited_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Invitee:
    id: int
    name: str
    email: str
    joined_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerCounts:
    total: int
    active: int
    invited_clients: int


@dataclass(frozen=True, slots=True, kw_only=True)
class OnboardedReseller:
    user_id: int
    created: bool
