from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from apps.accounts.domain.enums import (
    AddressLabel,
    Availability,
    NotificationChannel,
    NotificationTopic,
    ResellerOrdering,
)
from core.domain.actor import Role
from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterUser:
    first_name: str
    last_name: str
    email: str
    password: str
    phone_number: str | None = None
    referral_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateProfile:
    first_name: Maybe[str] = UNSET
    last_name: Maybe[str] = UNSET
    phone_number: Maybe[str | None] = UNSET
    avatar: Maybe[str] = UNSET
    referral_code: Maybe[str] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class AddressFields:
    label: AddressLabel
    recipient: str
    phone: str
    line1: str
    quarter: str
    city: str
    country: str
    is_default: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AddressChanges:
    label: Maybe[AddressLabel] = UNSET
    recipient: Maybe[str] = UNSET
    phone: Maybe[str] = UNSET
    line1: Maybe[str] = UNSET
    quarter: Maybe[str] = UNSET
    city: Maybe[str] = UNSET
    country: Maybe[str] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdatePreferences:
    preferences: Mapping[NotificationTopic, Mapping[NotificationChannel, bool]] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeRole:
    user_id: int
    role: Role


@dataclass(frozen=True, slots=True, kw_only=True)
class SetAvailability:
    availability: Availability


@dataclass(frozen=True, slots=True, kw_only=True)
class OnboardReseller:
    email: str
    first_name: str
    last_name: str
    phone_number: str | None = None
    commission_rate: Decimal | None = None
    manager_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerChanges:
    commission_rate: Maybe[Decimal] = UNSET
    manager_id: Maybe[int | None] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerFilters:
    search: str | None = None
    active: bool | None = None
    manager_id: int | None = None
    ordering: ResellerOrdering = ResellerOrdering.NAME
