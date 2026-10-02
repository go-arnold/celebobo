from dataclasses import dataclass
from datetime import datetime

from apps.accounts.domain.commands import UpdateProfile
from apps.accounts.domain.errors import (
    PhoneAlreadyUsed,
    ReferralAlreadySet,
    SelfReferral,
    StaffAccountDeletion,
    UserNotFound,
)
from apps.accounts.domain.normalization import clean_text, normalize_phone
from apps.accounts.models import User
from apps.accounts.services.contracts import AddressStore, UserStore
from apps.accounts.services.referrals import ReferralService
from core.domain.actor import Role
from core.domain.values import provided


@dataclass(frozen=True, slots=True)
class ProfileChange:
    user: User
    fields: tuple[str, ...]
    attached_reseller_id: int | None = None


class ProfileService:
    def __init__(
        self, users: UserStore, addresses: AddressStore, referrals: ReferralService
    ) -> None:
        self._users = users
        self._addresses = addresses
        self._referrals = referrals

    def update(self, user_id: int, command: UpdateProfile) -> ProfileChange:
        user = self._locked(user_id)
        changes = dict(provided(command))
        updated: list[str] = []
        attached_reseller_id = None

        if "referral_code" in changes:
            attached_reseller_id = self._attach_referral(user, changes.pop("referral_code"))
            updated.append("invited_by")
        for name in ("first_name", "last_name"):
            if name in changes:
                setattr(user, name, clean_text(changes[name]))
                updated.append(name)
        if "phone_number" in changes:
            user.phone_number = self._available_phone(user, changes["phone_number"])
            updated.append("phone_number")
        if "avatar" in changes:
            user.avatar = changes["avatar"]
            updated.append("avatar")

        if updated:
            self._users.save(user, fields=updated)
        return ProfileChange(user, tuple(updated), attached_reseller_id)

    def anonymize(self, user_id: int, *, now: datetime) -> User:
        user = self._locked(user_id)
        if user.account_role is not Role.CLIENT:
            raise StaffAccountDeletion
        user.email = f"deleted-{user.pk}@deleted.invalid"
        user.first_name = user.last_name = user.avatar = ""
        user.phone_number = None
        user.is_active = False
        user.deleted_at = now
        user.set_unusable_password()
        self._users.save(
            user,
            fields=(
                "email",
                "first_name",
                "last_name",
                "avatar",
                "phone_number",
                "is_active",
                "deleted_at",
                "password",
            ),
        )
        self._addresses.delete_all_for(user.pk)
        return user

    def _locked(self, user_id: int) -> User:
        user = self._users.get(user_id, for_update=True)
        if user is None or not user.is_active:
            raise UserNotFound
        return user

    def _attach_referral(self, user: User, code: str) -> int:
        if user.invited_by_id is not None:
            raise ReferralAlreadySet
        reseller = self._referrals.resolve(code)
        if reseller.pk == user.pk:
            raise SelfReferral
        user.invited_by = reseller
        return reseller.pk

    def _available_phone(self, user: User, phone: str | None) -> str | None:
        normalized = normalize_phone(phone)
        if normalized and self._users.phone_taken(normalized, exclude_id=user.pk):
            raise PhoneAlreadyUsed
        return normalized
