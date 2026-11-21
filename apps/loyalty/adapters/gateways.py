from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounts.selectors import ProfileSelector
from apps.content.facades import SiteContentFacade
from apps.loyalty.domain.membership import Requester
from apps.loyalty.domain.points import Purchase
from apps.loyalty.facades import PointsFacade
from apps.loyalty.repositories import MembershipRepository
from apps.orders.domain.enums import OrderStatus
from apps.orders.models import Order
from core.authz.catalog import permission_catalog
from core.container import container


class AccountsPeople:
    def requester(self, user_id: int) -> Requester:
        profile = ProfileSelector(permission_catalog).profile(user_id)
        name = f"{profile.first_name} {profile.last_name}".strip() or profile.email
        return Requester(
            id=profile.id,
            name=name,
            email_verified=profile.email_verified,
            phone=profile.phone_number,
        )


class LoyaltyMembers:
    def is_member(self, user_id: int) -> bool:
        return MembershipRepository().active(user_id, timezone.now())


class OrdersLedger:
    def purchase(self, order_id: int) -> Purchase | None:
        order = (
            Order.objects.filter(pk=order_id)
            .values("client_id", "subtotal", "discount", "points")
            .first()
        )
        if order is None:
            return None
        return Purchase(
            client_id=order["client_id"],
            base=order["subtotal"] - order["discount"] - order["points"],
            points_used=order["points"],
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
