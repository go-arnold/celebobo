from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from core.domain.actor import Role

ACCOUNT_ROLES = (Role.CLIENT, Role.RESELLER, Role.MANAGER, Role.ADMIN)

ROLE_LABELS = MappingProxyType(
    {
        Role.CLIENT: "Client",
        Role.RESELLER: "Revendeur",
        Role.MANAGER: "Responsable",
        Role.ADMIN: "Administrateur",
    }
)

STAFF_ROLES = frozenset({Role.MANAGER, Role.ADMIN})
MAX_COMMISSION_RATE = Decimal("0.500")


class Availability(StrEnum):
    ONLINE = "online"
    AWAY = "away"
    OFFLINE = "offline"

    @property
    def label(self) -> str:
        return {"online": "En ligne", "away": "Absent", "offline": "Hors ligne"}[self.value]


class AddressLabel(StrEnum):
    HOME = "home"
    OFFICE = "office"
    FAMILY = "family"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {"home": "Domicile", "office": "Bureau", "family": "Famille", "other": "Autre"}[
            self.value
        ]


class NotificationTopic(StrEnum):
    ORDER_ASSIGNED = "order_assigned"
    STATUS_CHANGED = "status_changed"
    NEW_MESSAGE = "new_message"
    PROMOTIONS = "promotions"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    PUSH = "push"


class ResellerOrdering(StrEnum):
    NAME = "name"
    NEWEST = "-joined"
    OLDEST = "joined"
    MOST_INVITED = "-invited"
    HIGHEST_RATE = "-rate"
