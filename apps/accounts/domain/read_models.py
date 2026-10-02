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
