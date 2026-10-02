from dataclasses import dataclass
from decimal import Decimal

from apps.resellers.domain.enums import ApplicationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitApplication:
    first_name: str
    last_name: str
    email: str
    phone_number: str
    city: str
    message: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ApproveApplication:
    commission_rate: Decimal | None = None
    manager_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RejectApplication:
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationFilters:
    status: ApplicationStatus | None = None
    search: str | None = None
