from typing import Any

import structlog

from core.domain.actor import Actor, Role

logger = structlog.get_logger(__name__)


def actor_from_user(user: Any) -> Actor:
    if user is None or not getattr(user, "is_authenticated", False):
        return Actor.anonymous()
    if getattr(user, "is_superuser", False):
        return Actor(role=Role.ADMIN, user_id=user.pk)
    return Actor(role=_role_of(user), user_id=user.pk)


def _role_of(user: Any) -> Role:
    raw = getattr(user, "role", Role.CLIENT)
    try:
        return Role(raw)
    except ValueError:
        logger.warning("actor.unknown_role", user_id=user.pk, role=raw)
        return Role.CLIENT
