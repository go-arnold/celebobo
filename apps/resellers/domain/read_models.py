from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.accounts.domain.read_models import ResellerAccount
from apps.resellers.domain.enums import ApplicationStatus
from apps.sales.domain.read_models import SellerPerformance


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationView:
    id: int
    first_name: str
    last_name: str
    email: str
    phone_number: str
    city: str
    message: str
    status: ApplicationStatus
    applicant_id: int | None
    reseller_id: int | None
    reviewed_by: PersonRef | None
    reviewed_at: datetime | None
    decision_note: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerOverview:
    account: ResellerAccount
    performance: SellerPerformance


@dataclass(frozen=True, slots=True, kw_only=True)
class TopReseller:
    id: int
    name: str
    revenue: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerStats:
    total: int
    active: int
    invited_clients: int
    pending_applications: int
    period_days: int
    top_reseller: TopReseller | None


@dataclass(frozen=True, slots=True, kw_only=True)
class InviteeView:
    id: int
    name: str
    email: str
    joined_at: datetime
    orders_count: int
    orders_total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class InviteesPage:
    code: str | None
    invited_count: int
    orders_total: Decimal
    invitees: list[InviteeView]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferralKit:
    code: str
    link: str
    qr_svg: str
    share_text: str
    whatsapp_url: str
