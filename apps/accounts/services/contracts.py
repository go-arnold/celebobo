from collections.abc import Collection, Iterable
from datetime import datetime
from typing import Any, Protocol

from apps.accounts.domain.consents import ConsentKind, ConsentSource
from apps.accounts.models import Address, Consent, User
from apps.audit.domain.retention import Expired
from core.domain.actor import Role


class UserStore(Protocol):
    def get(self, user_id: int, *, for_update: bool = False) -> User | None: ...

    def create(self, *, email: str, password: str, **fields: Any) -> User: ...

    def create_invited(self, *, email: str, **fields: Any) -> User: ...

    def by_email(self, email: str, *, for_update: bool = False) -> User | None: ...

    def active_staff(self, user_id: int) -> User | None: ...

    def save(self, user: User, *, fields: Iterable[str]) -> None: ...

    def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool: ...

    def phone_taken(self, phone_number: str, *, exclude_id: int | None = None) -> bool: ...

    def active_reseller_by_code(self, code: str) -> User | None: ...

    def referral_code_taken(self, code: str) -> bool: ...

    def signed_up_with_google(self, user_id: int) -> bool: ...


class AddressStore(Protocol):
    def get_for(
        self, user_id: int, address_id: int, *, for_update: bool = False
    ) -> Address | None: ...

    def count_for(self, user_id: int) -> int: ...

    def create(self, user_id: int, **fields: Any) -> Address: ...

    def save(self, address: Address, *, fields: Iterable[str]) -> None: ...

    def delete(self, address: Address) -> None: ...

    def clear_default(self, user_id: int) -> None: ...

    def newest_for(self, user_id: int) -> Address | None: ...

    def lock_owner(self, user_id: int) -> None: ...

    def delete_all_for(self, user_id: int) -> None: ...


class PreferenceStore(Protocol):
    def stored_for(self, user_id: int) -> dict[str, Any]: ...

    def store(self, user_id: int, preferences: dict[str, Any]) -> None: ...


class CodeGenerator(Protocol):
    def __call__(self) -> str: ...


class PasswordPolicy(Protocol):
    def validate(self, password: str, *, user: User | None = None) -> None: ...


class TokenRevoker(Protocol):
    def revoke_all(self, user_id: int) -> None: ...


class EmailVerifier(Protocol):
    def register_address(self, user: User, *, verified: bool = False) -> None: ...

    def send_verification(self, user_id: int) -> None: ...


class GroupSync(Protocol):
    def sync(self, user: User, role: Role) -> None: ...


class TicketStore(Protocol):
    def put(self, ticket: str, user_id: int, *, ttl: int) -> None: ...

    def take(self, ticket: str) -> int | None: ...


class PasswordSetupLinks(Protocol):
    def link_for(self, user: User) -> str: ...


class AvatarSource(Protocol):
    def url_for(self, owner_id: int, upload_id: int) -> str | None: ...


# account retention: when each user last did something in another part of the shop
class ActivitySource(Protocol):
    def last_activity(self, user_ids: Collection[int]) -> dict[int, datetime]: ...


# account retention: removes what another part of the shop holds about an anonymised client
class PersonalDataEraser(Protocol):
    def erase(self, user_id: int) -> None: ...


# the newsletter subscription of an e-mail address that is about to disappear (account deleted or
# anonymised); an opposition already expressed (unsubscribed address) stays
class NewsletterSubscriptions(Protocol):
    def forget(self, email: str) -> None: ...


class ConsentStore(Protocol):
    def accepted(self, user_id: int) -> dict[ConsentKind, str]: ...

    def any_for(self, user_id: int) -> bool: ...

    def create(
        self,
        user_id: int,
        *,
        kind: ConsentKind,
        version: str,
        source: ConsentSource,
        accepted_at: datetime,
    ) -> Consent: ...

    def withdraw(
        self, user_id: int, *, kinds: Iterable[ConsentKind], at: datetime
    ) -> tuple[ConsentKind, ...]: ...

    def quiet_marketing(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]: ...


class MarketingList(Protocol):
    """The newsletter, kept in step with the marketing consent."""

    def subscribe(self, email: str) -> None: ...

    def unsubscribe(self, email: str) -> None: ...

    def email_of(self, subscriber_id: int) -> str | None: ...
