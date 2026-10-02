from collections.abc import Iterable
from typing import Any

from django.db.models import QuerySet

from apps.accounts.models import Address, NotificationPreference, User
from core.domain.actor import Role


class UserRepository:
    def get(self, user_id: int, *, for_update: bool = False) -> User | None:
        queryset = User.objects.select_for_update() if for_update else User.objects.all()
        return queryset.filter(pk=user_id).first()

    def create(self, *, email: str, password: str, **fields: Any) -> User:
        return User.objects.create_user(email=email, password=password, **fields)

    def create_invited(self, *, email: str, **fields: Any) -> User:
        return User.objects.create_user(email=email, password=None, **fields)

    def by_email(self, email: str, *, for_update: bool = False) -> User | None:
        queryset = User.objects.select_for_update() if for_update else User.objects.all()
        return queryset.filter(email__iexact=email).first()

    def active_staff(self, user_id: int) -> User | None:
        return User.objects.filter(
            pk=user_id, is_active=True, role__in=[Role.MANAGER.value, Role.ADMIN.value]
        ).first()

    def save(self, user: User, *, fields: Iterable[str]) -> None:
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
