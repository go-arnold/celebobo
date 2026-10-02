from collections import defaultdict
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ImproperlyConfigured

from core.domain.actor import Actor, Role

type ObjectRule = Callable[[Actor, Any], bool]


class PermissionCatalog:
    def __init__(self) -> None:
        self._grants: defaultdict[Role, set[str]] = defaultdict(set)
        self._object_rules: dict[str, ObjectRule] = {}
        self._resolved: dict[Role, frozenset[str]] = {}

    def grant(self, role: Role, *permissions: str) -> None:
        self._grants[role].update(permissions)
        self._resolved.clear()

    def restrict(self, permission: str, rule: ObjectRule) -> None:
        self._ensure_known(permission)
        self._object_rules[permission] = rule

    def known(self) -> frozenset[str]:
        return frozenset().union(*self._grants.values())

    def permissions_for(self, role: Role) -> frozenset[str]:
        if role not in self._resolved:
            self._resolved[role] = frozenset(
                permission
                for granted_role, permissions in self._grants.items()
                if role.includes(granted_role)
                for permission in permissions
            )
        return self._resolved[role]

    def allows(self, actor: Actor, permission: str, obj: object | None = None) -> bool:
        self._ensure_known(permission)
        if permission not in self.permissions_for(actor.role):
            return False
        rule = self._object_rules.get(permission)
        return obj is None or rule is None or bool(rule(actor, obj))

    def clear(self) -> None:
        self._grants.clear()
        self._object_rules.clear()
        self._resolved.clear()

    def _ensure_known(self, permission: str) -> None:
        if permission not in self.known():
            raise ImproperlyConfigured(f"Unknown permission '{permission}'")


permission_catalog = PermissionCatalog()
