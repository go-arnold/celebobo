from apps.accounts.domain.enums import Availability
from apps.accounts.models import User
from apps.accounts.services.contracts import TokenRevoker, UserStore


class AccessService:
    def __init__(self, users: UserStore, revoker: TokenRevoker) -> None:
        self._users = users
        self._revoker = revoker

    def set_active(self, user: User, *, active: bool) -> bool:
        if user.is_active is active:
            return False
        user.is_active = active
        user.availability = Availability.OFFLINE.value
        self._users.save(user, fields=("is_active", "availability"))
        if not active:
            self._revoker.revoke_all(user.pk)
        return True
