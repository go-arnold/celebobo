from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class Role(StrEnum):
    ANONYMOUS = "anonymous"
    CLIENT = "client"
    RESELLER = "reseller"
    MANAGER = "manager"
    ADMIN = "admin"
    SYSTEM = "system"

    @property
    def rank(self) -> int:
        return _RANKS[self]

    def includes(self, other: "Role") -> bool:
        return self.rank >= other.rank


_RANKS = {
    Role.ANONYMOUS: 0,
    Role.CLIENT: 1,
    Role.RESELLER: 2,
    Role.MANAGER: 3,
    Role.ADMIN: 4,
    Role.SYSTEM: 5,
}


@dataclass(frozen=True, slots=True)
class Actor:
    role: Role
    user_id: int | None = None

    @classmethod
    def anonymous(cls) -> Self:
        return cls(role=Role.ANONYMOUS)

    @classmethod
    def system(cls) -> Self:
        return cls(role=Role.SYSTEM)

    @property
    def is_authenticated(self) -> bool:
        return self.role is not Role.ANONYMOUS

    @property
    def is_backoffice(self) -> bool:
        return self.role.includes(Role.RESELLER)

    @property
    def is_staff(self) -> bool:
        return self.role.includes(Role.MANAGER)

    def owns(self, owner_id: int | None) -> bool:
        return self.user_id is not None and self.user_id == owner_id
