from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from allauth.socialaccount.models import SocialAccount
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.accounts.domain.consents import ConsentKind, ConsentSource
from apps.accounts.domain.errors import PhoneAlreadyUsed
from apps.accounts.models import Address, Consent, NotificationPreference, User
from apps.audit.domain.retention import Expired
from core.domain.actor import Role

PHONE_CONSTRAINT = "accounts_user_phone_unique"


# the services check `phone_taken` first, but another account may take the number between that
# check and the save: the unique constraint then refuses it, reported like the check would
@contextmanager
def _unique_phone() -> Iterator[None]:
    try:
        with transaction.atomic():
            yield
    except IntegrityError as error:
        if PHONE_CONSTRAINT in str(error):
            raise PhoneAlreadyUsed from error
        raise


class UserRepository:
    def get(self, user_id: int, *, for_update: bool = False) -> User | None:
        queryset = User.objects.select_for_update() if for_update else User.objects.all()
        return queryset.filter(pk=user_id).first()

    def create(self, *, email: str, password: str, **fields: Any) -> User:
        with _unique_phone():
            return User.objects.create_user(email=email, password=password, **fields)

    def create_invited(self, *, email: str, **fields: Any) -> User:
        with _unique_phone():
            return User.objects.create_user(email=email, password=None, **fields)

    def by_email(self, email: str, *, for_update: bool = False) -> User | None:
        queryset = User.objects.select_for_update() if for_update else User.objects.all()
        return queryset.filter(email__iexact=email).first()

    def active_staff(self, user_id: int) -> User | None:
        return User.objects.filter(
            pk=user_id, is_active=True, role__in=[Role.MANAGER.value, Role.ADMIN.value]
        ).first()

    def save(self, user: User, *, fields: Iterable[str]) -> None:
        with _unique_phone():
            user.save(update_fields=[*fields])

    def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool:
        return self._others(exclude_id).filter(email__iexact=email).exists()

    def phone_taken(self, phone_number: str, *, exclude_id: int | None = None) -> bool:
        return self._others(exclude_id).filter(phone_number=phone_number).exists()

    def active_reseller_by_code(self, code: str) -> User | None:
        return User.objects.filter(
            referral_code=code, role=Role.RESELLER.value, is_active=True
        ).first()

    def referral_code_taken(self, code: str) -> bool:
        return User.objects.filter(referral_code=code).exists()

    def signed_up_with_google(self, user_id: int) -> bool:
        return bool(SocialAccount.objects.filter(user_id=user_id, provider="google").exists())

    @staticmethod
    def _others(exclude_id: int | None) -> QuerySet[User]:
        return User.objects.exclude(pk=exclude_id) if exclude_id else User.objects.all()


class AddressRepository:
    def list_for(self, user_id: int) -> list[Address]:
        return list(Address.objects.filter(user_id=user_id))

    def get_for(self, user_id: int, address_id: int, *, for_update: bool = False) -> Address | None:
        queryset = Address.objects.select_for_update() if for_update else Address.objects.all()
        return queryset.filter(user_id=user_id, pk=address_id).first()

    def count_for(self, user_id: int) -> int:
        return Address.objects.filter(user_id=user_id).count()

    def create(self, user_id: int, **fields: Any) -> Address:
        return Address.objects.create(user_id=user_id, **fields)

    def save(self, address: Address, *, fields: Iterable[str]) -> None:
        address.save(update_fields=[*fields, "updated_at"])

    def delete(self, address: Address) -> None:
        address.delete()

    def clear_default(self, user_id: int) -> None:
        Address.objects.filter(user_id=user_id, is_default=True).update(is_default=False)

    def newest_for(self, user_id: int) -> Address | None:
        return Address.objects.filter(user_id=user_id).order_by("-created_at", "-pk").first()

    def lock_owner(self, user_id: int) -> None:
        list(User.objects.select_for_update().filter(pk=user_id).values_list("pk", flat=True))

    def delete_all_for(self, user_id: int) -> None:
        Address.objects.filter(user_id=user_id).delete()


class PreferenceRepository:
    def stored_for(self, user_id: int) -> dict[str, Any]:
        record = NotificationPreference.objects.filter(user_id=user_id).first()
        return dict(record.preferences) if record else {}

    def store(self, user_id: int, preferences: dict[str, Any]) -> None:
        NotificationPreference.objects.update_or_create(
            user_id=user_id, defaults={"preferences": preferences}
        )


# account retention: plain client accounts (no staff, no reseller, past or present) not yet
# anonymised, without sign-up or login since the cutoff; and client accounts deleted before the
# cutoff whose remaining personal data were not erased yet
class InactiveClientRepository:
    def due(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        rows = (
            _due(cutoff)
            .filter(pk__gt=after_id)
            .order_by("pk")
            .values_list("pk", "deleted_at", "date_joined", "last_login", "last_seen_at")[:limit]
        )
        return [
            Expired(
                pk,
                f"compte client #{pk}, supprimé le {deleted:%Y-%m-%d}"
                if deleted
                else f"compte client #{pk}, vu pour la dernière fois le {_latest(*dates):%Y-%m-%d}",
            )
            for pk, deleted, *dates in rows
        ]

    def lock_due(self, user_id: int, cutoff: datetime) -> User | None:
        return _due(cutoff).select_for_update().filter(pk=user_id).first()

    def save(self, user: User, *, fields: Iterable[str]) -> None:
        user.save(update_fields=[*fields])

    def forget_preferences(self, user_id: int) -> None:
        NotificationPreference.objects.filter(user_id=user_id).delete()


def _latest(*dates: datetime | None) -> datetime:
    return max(date for date in dates if date is not None)


def _due(cutoff: datetime) -> QuerySet[User]:
    quiet = (
        Q(deleted_at__isnull=True, referral_code__isnull=True, date_joined__lt=cutoff)
        & ~Q(last_login__gte=cutoff)
        & ~Q(last_seen_at__gte=cutoff)
    )
    deleted_long_ago = Q(deleted_at__lt=cutoff)
    return User.objects.filter(
        quiet | deleted_long_ago,
        role=Role.CLIENT.value,
        is_staff=False,
        is_superuser=False,
        personal_data_erased_at__isnull=True,
    )


class ConsentRepository:
    def accepted(self, user_id: int) -> dict[ConsentKind, str]:
        return Consent.objects.open_versions(user_id)

    def any_for(self, user_id: int) -> bool:
        return Consent.objects.filter(user_id=user_id).exists()

    def create(
        self,
        user_id: int,
        *,
        kind: ConsentKind,
        version: str,
        source: ConsentSource,
        accepted_at: datetime,
    ) -> Consent:
        return Consent.objects.create(
            user_id=user_id,
            kind=kind.value,
            version=version,
            source=source.value,
            accepted_at=accepted_at,
        )

    def withdraw(
        self, user_id: int, *, kinds: Iterable[ConsentKind], at: datetime
    ) -> tuple[ConsentKind, ...]:
        rows = Consent.objects.filter(
            user_id=user_id, kind__in=[kind.value for kind in kinds], withdrawn_at__isnull=True
        )
        withdrawn = {ConsentKind(kind) for kind in rows.values_list("kind", flat=True)}
        rows.update(withdrawn_at=at)
        return tuple(kind for kind in ConsentKind if kind in withdrawn)
