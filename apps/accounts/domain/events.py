from apps.accounts.domain.enums import Availability
from core.domain.actor import Role
from core.events.base import DomainEvent, domain_event


@domain_event
class UserRegistered(DomainEvent):
    user_id: int
    invited_by_id: int | None = None
    via_social: bool = False


@domain_event
class ReferralAttached(DomainEvent):
    user_id: int
    reseller_id: int


@domain_event
class ProfileUpdated(DomainEvent):
    user_id: int
    fields: tuple[str, ...]


@domain_event
class RoleChanged(DomainEvent):
    user_id: int
    previous_role: Role
    role: Role


@domain_event
class AvailabilityChanged(DomainEvent):
    user_id: int
    availability: Availability


@domain_event
class AccountDeleted(DomainEvent):
    user_id: int
