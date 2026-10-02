from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from core.api.actor import actor_from_user
from core.authz.catalog import PermissionCatalog, permission_catalog
from core.domain.actor import Actor


def requires(
    *permissions: str, any_of: bool = False, catalog: PermissionCatalog | None = None
) -> type[BasePermission]:
    if not permissions:
        raise ValueError("requires() needs at least one permission")
    match = any if any_of else all

    def check(actor: Actor, obj: object | None = None) -> bool:
        source = catalog or permission_catalog
        return match(source.allows(actor, permission, obj) for permission in permissions)

    class RequiresPermission(BasePermission):
        required = permissions

        def has_permission(self, request: Request, view: APIView) -> bool:
            return check(_actor(request, view))

        def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
            return check(_actor(request, view), obj)

    joiner = " | " if any_of else " & "
    RequiresPermission.__name__ = f"Requires({joiner.join(permissions)})"
    RequiresPermission.__qualname__ = RequiresPermission.__name__
    return RequiresPermission


def _actor(request: Request, view: APIView) -> Actor:
    actor = getattr(view, "actor", None)
    return actor if isinstance(actor, Actor) else actor_from_user(request.user)
