from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.cache import caches
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.domain.enums import ACCOUNT_ROLES
from apps.accounts.domain.errors import WeakPassword
from apps.accounts.models import User
from core.domain.actor import Role


class DjangoPasswordPolicy:
    def validate(self, password: str, *, user: User | None = None) -> None:
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise WeakPassword(list(exc.messages)) from exc


class SimpleJwtTokenRevoker:
    def revoke_all(self, user_id: int) -> None:
        outstanding = OutstandingToken.objects.filter(
            user_id=user_id, blacklistedtoken__isnull=True
        )
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=token) for token in outstanding], ignore_conflicts=True
        )


class DjangoGroupSync:
    def sync(self, user: User, role: Role) -> None:
        role_groups = Group.objects.filter(name__in=[item.value for item in ACCOUNT_ROLES])
        user.groups.remove(*role_groups)
        if role is not Role.CLIENT:
            group, _ = Group.objects.get_or_create(name=role.value)
            user.groups.add(group)


class CacheTicketStore:
    def __init__(self, cache_alias: str = "default") -> None:
        self._cache_alias = cache_alias

    def put(self, ticket: str, user_id: int, *, ttl: int) -> None:
        caches[self._cache_alias].set(self._key(ticket), user_id, timeout=ttl)

    def take(self, ticket: str) -> int | None:
        cache = caches[self._cache_alias]
        key = self._key(ticket)
        user_id = cache.get(key)
        if user_id is None or not cache.delete(key):
            return None
        return int(user_id)

    @staticmethod
    def _key(ticket: str) -> str:
        return f"accounts:ws-ticket:{ticket}"
