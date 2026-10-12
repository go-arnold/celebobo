import calendar
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Plan(StrEnum):
    TRIAL = "trial"
    MONTHLY = "monthly"
    YEARLY = "yearly"


PAID_MONTHS = {Plan.MONTHLY: 1, Plan.YEARLY: 12}


class MembershipStatus(StrEnum):
    NONE = "none"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"


class RequestStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def membership_status(plan: str, ends_at: datetime | None, now: datetime) -> MembershipStatus:
    if ends_at is None:
        return MembershipStatus.NONE
    if ends_at <= now:
        return MembershipStatus.EXPIRED
    return MembershipStatus.TRIAL if plan == Plan.TRIAL else MembershipStatus.ACTIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class Requester:
    id: int
    name: str
    email_verified: bool
    phone: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberRef:
    id: int
    name: str
    email: str
    phone: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestView:
    id: int
    plan: Plan
    price: Decimal
    payment_method: str
    status: RequestStatus
    note: str
    created_at: datetime
    handled_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberView:
    status: MembershipStatus
    plan: Plan | None
    ends_at: datetime | None
    trial_available: bool
    pending_request: RequestView | None


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminRequestRow:
    request: RequestView
    member: MemberRef


@dataclass(frozen=True, slots=True, kw_only=True)
class AdminMemberRow:
    member: MemberRef
    status: MembershipStatus
    plan: Plan
    ends_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestMembership:
    plan: Plan
    payment_method: str
