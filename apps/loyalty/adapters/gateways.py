from decimal import Decimal

from apps.accounts.selectors import ProfileSelector
from apps.content.facades import SiteContentFacade
from apps.loyalty.domain.cashback import Purchase
from apps.loyalty.facades import CashbackFacade
from core.authz.catalog import permission_catalog
from core.container import container


class AccountsPeople:
    def requester(self, user_id: int) -> Purchase:
        profile = ProfileSelector(permission_catalog).profile(user_id)
        return Purchase(
            client_id=profile.id,
            base=Decimal("0"),
            cashback_used=Decimal("0"),
        )


class OrdersLedger:
    def purchase(self, order_id: int) -> Purchase | None:
        from apps.orders.models import Order

        order = (
            Order.objects.filter(pk=order_id)
            .values("client_id", "subtotal", "discount", "cashback")
            .first()
        )
        if order is None:
            return None
        return Purchase(
            client_id=order["client_id"],
            base=order["subtotal"] - order["discount"] - order["cashback"],
            cashback_used=order["cashback"],
        )


class ContentReturnPolicy:
    def return_days(self) -> int:
        return container.resolve(SiteContentFacade).public_settings().return_days


class LoyaltyWallet:
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return container.resolve(CashbackFacade).usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        container.resolve(CashbackFacade).spend(user_id, order_id, amount)

    def earned(self, order_id: int) -> Decimal | None:
        return container.resolve(CashbackFacade).earned(order_id)
