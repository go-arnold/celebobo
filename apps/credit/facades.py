from decimal import Decimal

from django.db import transaction

from apps.credit.domain.rules import CreditBalance
from apps.credit.selectors import CreditSelector
from apps.credit.services.credit import StoreCreditService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.observability.decorators import logged_facade

CHANGE_OF_MIND = "Avoir : changement d'avis pendant le délai d'essai"


@logged_facade
class StoreCreditFacade:
    def __init__(self, *, credit: StoreCreditService, selector: CreditSelector) -> None:
        self._credit = credit
        self._selector = selector

    def balance(self, actor: Actor) -> CreditBalance:
        if actor.user_id is None:
            raise Unauthenticated
        return self._selector.balance(actor.user_id)

    # an order was cancelled or returned: the credit it used goes back
    def order_undone(self, order_id: int) -> None:
        self._credit.give_back(order_id, note="Commande annulée ou retournée")

    # units of a line came back: their share of the credit goes back; for a change of mind during
    # the trial the money paid for them becomes store credit too
    def line_returned(
        self,
        client_id: int,
        order_id: int | None,
        *,
        credit: Decimal,
        paid: Decimal,
        as_credit: bool,
    ) -> None:
        with transaction.atomic():
            if credit > 0 and order_id is not None:
                self._credit.give_back(order_id, credit, note="Article retourné")
            if as_credit:
                self._credit.issue(client_id, paid, note=CHANGE_OF_MIND, order_id=order_id)

    # the order's price went down: credit it no longer needs goes back
    def repriced(self, order_id: int, store_credit: Decimal) -> None:
        excess = self._credit.spent_on(order_id) - store_credit
        if excess > 0:
            self._credit.give_back(order_id, excess, note="Prix de la commande baissé")

    def expire(self) -> int:
        return self._credit.expire()
