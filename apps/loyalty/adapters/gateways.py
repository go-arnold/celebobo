from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Sum

from apps.accounts.selectors import ReferralSelector
from apps.content.facades import SiteContentFacade
from apps.loyalty.domain.points import Purchase, Referral
from apps.loyalty.facades import PointsFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.models import Order
from core.container import container


class OrdersLedger:
    def purchase(self, order_id: int) -> Purchase | None:
        order = (
            Order.objects.filter(pk=order_id)
            .values("client_id", "subtotal", "discount", "points", "store_credit", "created_at")
            .first()
        )
        if order is None:
            return None
        products = order["subtotal"] - order["discount"] - order["points"]
        return Purchase(
            client_id=order["client_id"],
            # what the client paid for the products in money: store credit pays them first
            base=products - min(order["store_credit"], products),
            points_used=order["points"],
            discount=order["discount"],
            store_credit=order["store_credit"],
            placed_at=order["created_at"],
        )

    def delivered(self, client_id: int) -> tuple[int, Decimal]:
        totals = Order.objects.filter(
            client_id=client_id, status=OrderStatus.DELIVERED.value
        ).aggregate(count=Count("pk"), total=Sum("total"))
        return totals["count"] or 0, totals["total"] or Decimal(0)

    def last_purchase(self, client_id: int) -> datetime | None:
        return (
            Order.objects.filter(client_id=client_id)
            .exclude(status=OrderStatus.CANCELLED.value)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )


class ContentReturnPolicy:
    def return_days(self) -> int:
        return container.resolve(SiteContentFacade).public_settings().return_days


class LoyaltyWallet:
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return container.resolve(PointsFacade).usable(user_id, base, lock=lock)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        container.resolve(PointsFacade).spend(user_id, order_id, amount)

    def earned(self, order_id: int) -> Decimal | None:
        return container.resolve(PointsFacade).earned(order_id)


class AccountsReferrals:
    def referral(self, client_id: int) -> Referral | None:
        found = ReferralSelector().referral(client_id)
        if found is None:
            return None
        return Referral(reseller_id=found.reseller_id, since=found.since)
