from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction

from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.numbers import new_order_number
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatusEvent

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
