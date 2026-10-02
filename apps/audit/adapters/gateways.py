from collections.abc import Sequence

from apps.accounts.selectors import SellerSelector


class AccountActorNames:
    def names(self, ids: Sequence[int]) -> dict[int, str]:
        return SellerSelector().names(ids) if ids else {}
