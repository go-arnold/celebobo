from dataclasses import dataclass
from datetime import datetime

from apps.accounts.domain.consents import ConsentKind, ConsentSource
from apps.accounts.domain.enums import AddressLabel, Availability
from core.domain.actor import Role


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerProfile:
    referral_code: str | None
    availability: Availability
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
    # required consents still to give before the account can be used (completion step)
    missing_consents: tuple[ConsentKind, ...] = ()
    # a client or reseller without a phone number (completion step)
    phone_required: bool = False


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


@dataclass(frozen=True, slots=True, kw_only=True)
class InviterRef:
    id: int
    name: str
    referral_code: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class UserRow:
    id: int
    first_name: str
    last_name: str
    name: str
    email: str
    phone_number: str | None
    avatar: str
    role: Role
    referral_code: str | None
    invited_by: InviterRef | None
    is_active: bool
    email_verified: bool
    date_joined: datetime
    last_login: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Referral:
    """The active reseller who invited a client, and since when."""

    reseller_id: int
    since: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class InvitingReseller:
    """The active reseller who invited a client, with no time limit (assignment suggestion)."""

    id: int
    name: str
    invited_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsentRecord:
    """One acceptance, as kept for proof."""

    kind: ConsentKind
    version: str
    source: ConsentSource
    accepted_at: datetime
    withdrawn_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsentStatus:
    kind: ConsentKind
    label: str
    required: bool
    given: bool
    # the last acceptance still open, if any
    version: str | None
    accepted_at: datetime | None
    source: ConsentSource | None
    current_version: str
    # given on an older version of the document: to accept again
    outdated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsentOverview:
    consents: tuple[ConsentStatus, ...]
    missing: tuple[ConsentKind, ...]
    history: tuple[ConsentRecord, ...]
