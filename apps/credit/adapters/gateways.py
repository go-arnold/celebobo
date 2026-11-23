from decimal import Decimal

from apps.credit.services.credit import StoreCreditService


class StoreCreditWallet:
    """The orders' `CreditWallet`: what a client may use at checkout, and spending it."""

    def __init__(self, credit: StoreCreditService) -> None:
        self._credit = credit

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return self._credit.usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        self._credit.spend(user_id, order_id, amount)
