from typing import Any
from urllib.parse import parse_qs

from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.accounts.facades import RealtimeAccessFacade
from apps.realtime.adapters.db import db_call
from core.container import container

TICKET_PARAMETER = "ticket"


class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = (query.get(TICKET_PARAMETER) or [""])[0]
        scope["user"] = await _user_for(ticket)
        return await super().__call__(scope, receive, send)


@db_call
def _user_for(ticket: str) -> Any:
    if not ticket:
        return AnonymousUser()
    user_id = container.resolve(RealtimeAccessFacade).redeem_ticket(ticket)
    if user_id is None:
        return AnonymousUser()
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    return user or AnonymousUser()
