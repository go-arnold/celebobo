from typing import Any

from auditlog.context import auditlog_value
from django.contrib.auth import get_user_model

from core.api.signals import request_authenticated
from core.domain.actor import Actor


def attach_actor(*, request: Any, actor: Actor, **_: Any) -> None:
    user = getattr(request, "user", None)
    if actor.user_id is None or not isinstance(user, get_user_model()):
        return
    try:
        context = auditlog_value.get()
    except LookupError:
        return
    context["actor"] = user


def connect() -> None:
    request_authenticated.connect(attach_actor, dispatch_uid="audit.attach_actor")
