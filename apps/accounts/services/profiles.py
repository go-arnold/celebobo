from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.accounts.domain.commands import UpdateProfile
from apps.accounts.domain.errors import (
    InvalidAvatar,
    PhoneAlreadyUsed,
    ReferralAlreadySet,
    SelfReferral,
    StaffAccountDeletion,
    UserNotFound,
)
from apps.accounts.domain.normalization import clean_text, normalize_phone
from apps.accounts.domain.retention import anonymized_email
from apps.accounts.models import User
from apps.accounts.services.contracts import AddressStore, AvatarSource, UserStore
from apps.accounts.services.referrals import ReferralService
from core.domain.actor import Role
from core.domain.values import provided


# what identifies the client on the account itself goes, and the account can no longer be used;
# the e-mail placeholder stays unique per account (returns the fields changed)
def scrub_identity(user: User, now: datetime) -> tuple[str, ...]:
    user.email = anonymized_email(user.pk)
    user.first_name = user.last_name = user.avatar = ""
    user.phone_number = None
    user.referral_code = None
    user.is_active = False
    user.deleted_at = now
    user.set_unusable_password()
    return (
        "email",
        "first_name",
        "last_name",
        "avatar",
        "phone_number",
        "referral_code",
        "is_active",
        "deleted_at",
        "password",
    )


@dataclass(frozen=True, slots=True)
class ProfileChange:
    user: User
    fields: tuple[str, ...]
    attached_reseller_id: int | None = None


class ProfileService:
    def __init__(
        self,
        users: UserStore,
        addresses: AddressStore,
        referrals: ReferralService,
        avatars: AvatarSource,
    ) -> None:
        self._users = users
        self._addresses = addresses
        self._referrals = referrals
        self._avatars = avatars

    def update(self, user_id: int, command: UpdateProfile) -> ProfileChange:
        user = self._locked(user_id)
        changes = dict(provided(command))
        updated: list[str] = []
        attached_reseller_id = None

        if "referral_code" in changes:
            attached_reseller_id = self._attach_referral(user, changes.pop("referral_code"))
            updated.extend(("invited_by", "invited_at"))
        for name in ("first_name", "last_name"):
            if name in changes:
                setattr(user, name, clean_text(changes[name]))
                updated.append(name)
        if "phone_number" in changes:
            user.phone_number = self._available_phone(user, changes["phone_number"])
            updated.append("phone_number")
        if "avatar_upload_id" in changes:
            user.avatar = self._avatar(user.pk, changes["avatar_upload_id"])
            updated.append("avatar")

        if updated:
            self._users.save(user, fields=updated)
        return ProfileChange(user, tuple(updated), attached_reseller_id)

    def _avatar(self, user_id: int, upload_id: int | None) -> str:
        if upload_id is None:
            return ""
        url = self._avatars.url_for(user_id, upload_id)
        if url is None:
            raise InvalidAvatar
        return url

    def anonymize(self, user_id: int, *, now: datetime) -> User:
        user = self._locked(user_id)
        if user.account_role is not Role.CLIENT:
            raise StaffAccountDeletion
        self._users.save(user, fields=scrub_identity(user, now))
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
        user.invited_at = timezone.now()
        return reseller.pk

    def _available_phone(self, user: User, phone: str | None) -> str | None:
        normalized = normalize_phone(phone)
        if normalized and self._users.phone_taken(normalized, exclude_id=user.pk):
            raise PhoneAlreadyUsed
        return normalized
