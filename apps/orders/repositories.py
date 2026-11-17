from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import IntegrityError, connection, transaction
from django.db.models import F, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.numbers import new_order_number
from apps.orders.models import (
    Cart,
    CartItem,
    Coupon,
    CouponRedemption,
    Order,
    OrderItem,
    OrderStatusEvent,
    ShippingZone,
)

CLIENT_LOCK = 7301  # advisory lock namespace for checkouts
NUMBER_ATTEMPTS = 5


class CartRepository:
    def for_user(self, user_id: int) -> Cart | None:
        return Cart.objects.filter(user_id=user_id).first()

    def ensure_for_user(self, user_id: int) -> Cart:
        cart, _ = Cart.objects.get_or_create(user_id=user_id)
        return cart

    def for_token(self, token: UUID) -> Cart | None:
        return Cart.objects.filter(token=token, user__isnull=True).first()

    def create_guest(self) -> Cart:
        return Cart.objects.create()

    def items(self, cart: Cart) -> list[CartItem]:
        return list(cart.items.all())

    def item(self, cart: Cart, item_id: int) -> CartItem | None:
        return cart.items.filter(pk=item_id).first()

    def add(
        self, cart: Cart, *, product_id: int, variant_id: int | None, quantity: int
    ) -> CartItem:
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product_id=product_id,
            variant_id=variant_id,
            defaults={"quantity": quantity},
        )
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])
        cart.save(update_fields=["updated_at"])
        return item

    def set_quantity(self, item: CartItem, quantity: int) -> CartItem:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        return item

    def save_cart(self, cart: Cart, *, fields: Iterable[str]) -> None:
        cart.save(update_fields=[*fields, "updated_at"])

    def remove(self, item: CartItem) -> None:
        item.delete()

    def clear(self, cart: Cart) -> None:
        cart.items.all().delete()

    def delete(self, cart: Cart) -> None:
        cart.delete()


class OrderRepository:
    def create(self, **fields: Any) -> Order:
        for attempt in range(NUMBER_ATTEMPTS):
            try:
                with transaction.atomic():
                    return Order.objects.create(number=new_order_number(), **fields)
            except IntegrityError:
                if attempt == NUMBER_ATTEMPTS - 1:
                    raise
        raise RuntimeError("unreachable")

    def add_items(self, order: Order, items: Iterable[dict[str, Any]]) -> list[OrderItem]:
        return OrderItem.objects.bulk_create(OrderItem(order=order, **item) for item in items)

    def get(self, order_id: int, *, for_update: bool = False) -> Order | None:
        queryset = Order.objects.select_for_update() if for_update else Order.objects.all()
        return queryset.filter(pk=order_id).first()

    def for_client(self, client_id: int, number: str, *, for_update: bool = False) -> Order | None:
        queryset = Order.objects.select_for_update() if for_update else Order.objects.all()
        return queryset.filter(client_id=client_id, number=number).first()

    def items(self, order: Order) -> list[OrderItem]:
        return list(order.items.all())

    # serialises a client's checkouts until the transaction ends, so the pending cap holds
    def lock_client(self, client_id: int) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [CLIENT_LOCK, client_id])

    def pending_count(self, client_id: int) -> int:
        return Order.objects.filter(client_id=client_id, status=OrderStatus.PENDING.value).count()

    def stale_pending(self, cutoff: datetime) -> list[int]:
        return list(_pending_since(cutoff).order_by("pk").values_list("pk", flat=True))

    def stale(self, order_id: int, cutoff: datetime) -> Order | None:
        return _pending_since(cutoff).select_for_update(of=("self",)).filter(pk=order_id).first()

    def save(self, order: Order, *, fields: Iterable[str]) -> None:
        order.save(update_fields=[*fields, "updated_at"])

    def record(
        self,
        order: Order,
        *,
        previous: OrderStatus | None,
        status: OrderStatus,
        actor_id: int | None,
        actor_role: str,
        note: str = "",
    ) -> OrderStatusEvent:
        return OrderStatusEvent.objects.create(
            order=order,
            from_status=previous.value if previous else "",
            to_status=status.value,
            actor_id=actor_id,
            actor_role=actor_role,
            note=note[:500],
        )

    def item(self, order: Order, item_id: int) -> OrderItem | None:
        return order.items.filter(pk=item_id).first()

    def save_item(self, item: OrderItem, *, fields: Iterable[str]) -> None:
        item.save(update_fields=[*fields])


class ShippingZoneRepository:
    def active(self) -> list[ShippingZone]:
        return list(ShippingZone.objects.filter(is_active=True))


class CouponRepository:
    def by_code(self, code: str, *, for_update: bool = False) -> Coupon | None:
        queryset = Coupon.objects.select_for_update() if for_update else Coupon.objects.all()
        return queryset.filter(code__iexact=code.strip()).first()

    def usage(self, coupon: Coupon, user_id: int | None) -> tuple[int, int]:
        live = CouponRedemption.objects.filter(coupon=coupon).exclude(
            order__status=OrderStatus.CANCELLED.value
        )
        return live.count(), live.filter(user_id=user_id).count() if user_id else 0

    def redeem(self, coupon: Coupon, order: Order, *, user_id: int, amount: Decimal) -> None:
        CouponRedemption.objects.create(coupon=coupon, order=order, user_id=user_id, amount=amount)


# a pending order counts from the last time it became pending (placed, or declined by a reseller)
def _pending_since(cutoff: datetime) -> QuerySet[Order]:
    entered = (
        OrderStatusEvent.objects.filter(order=OuterRef("pk"), to_status=OrderStatus.PENDING.value)
        .order_by("-created_at", "-pk")
        .values("created_at")[:1]
    )
    return (
        Order.objects.filter(status=OrderStatus.PENDING.value)
        .annotate(pending_since=Coalesce(Subquery(entered), F("created_at")))
        .filter(pending_since__lte=cutoff)
    )
