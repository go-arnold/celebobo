import secrets

from apps.accounts.domain.read_models import WsTicket
from apps.accounts.services.contracts import TicketStore

DEFAULT_TICKET_TTL = 30


class TicketService:
    def __init__(self, store: TicketStore, *, ttl: int = DEFAULT_TICKET_TTL) -> None:
        self._store = store
        self._ttl = ttl

    def issue(self, user_id: int) -> WsTicket:
        ticket = secrets.token_urlsafe(32)
        self._store.put(ticket, user_id, ttl=self._ttl)
        return WsTicket(ticket=ticket, expires_in=self._ttl)

    def redeem(self, ticket: str) -> int | None:
        return self._store.take(ticket) if ticket else None
