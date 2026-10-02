from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.orders.domain.commands import (
    AssignOrder,
    CancelOrder,
    CouponChanges,
    CouponFields,
    DeclineAssignment,
    OrderFilters,
    OrderLineInput,
    PlaceOrder,
    TrackOrder,
    TransitionOrder,
    ZoneChanges,
    ZoneFields,
)
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import OrderNotFound
from apps.orders.domain.events import (
    AssignmentDeclined,
    OrderAssigned,
    OrderPlaced,
    OrderRepriced,
    OrderStatusChanged,
)
from apps.orders.domain.numbers import normalize_order_number
from apps.orders.domain.read_models import (
    AdjustableItem,
    AssignableReseller,
    CartView,
    CouponView,
    OrderDetail,
    OrderSummary,
    QuoteView,
    ShippingZoneView,
    TrackingView,
)
from apps.orders.models import Order
from apps.orders.repositories import CartRepository, OrderRepository
from apps.orders.selectors import OrderSelector, PromotionSelector, scoped_orders
from apps.orders.services.adjustments import AdjustmentService
from apps.orders.services.cart import CartOwner, CartService
from apps.orders.services.checkout import CheckoutService
from apps.orders.services.contracts import OrderThreads, ResellerDirectory
from apps.orders.services.lifecycle import OrderLifecycleService, StatusChange
from apps.orders.services.pricing import PricingContext, PricingService
from apps.orders.services.promotions import CouponAdminService, ShippingZoneService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@dataclass(frozen=True, slots=True)
class OrderPage:
    orders: list[OrderSummary]
    total: int
    counts: dict[str, int]


@logged_facade
class CartFacade:
    def __init__(self, *, carts: CartService) -> None:
        self._carts = carts

    def view(self, actor: Actor, token: UUID | None, *, city: str | None = None) -> CartView:
        return self._carts.view(_owner(actor, token, city=city))

    def apply_coupon(self, actor: Actor, token: UUID | None, code: str) -> CartView:
        with transaction.atomic():
            return self._carts.apply_coupon(_owner(actor, token), code)

    def remove_coupon(self, actor: Actor, token: UUID | None) -> CartView:
        with transaction.atomic():
            return self._carts.remove_coupon(_owner(actor, token))

    def add(self, actor: Actor, token: UUID | None, line: OrderLineInput) -> CartView:
        with transaction.atomic():
            return self._carts.add(_owner(actor, token), line)

    def update(self, actor: Actor, token: UUID | None, item_id: int, quantity: int) -> CartView:
        with transaction.atomic():
            return self._carts.update(_owner(actor, token), item_id, quantity)

    def remove(self, actor: Actor, token: UUID | None, item_id: int) -> CartView:
        with transaction.atomic():
            return self._carts.remove(_owner(actor, token), item_id)

    def clear(self, actor: Actor, token: UUID | None) -> None:
        with transaction.atomic():
            self._carts.clear(_owner(actor, token))

    def merge(self, actor: Actor, token: UUID) -> CartView:
        with transaction.atomic():
            return self._carts.merge(_user_id(actor), token)


@logged_facade
class CheckoutFacade:
    def __init__(
        self,
        *,
        checkout: CheckoutService,
        pricing: PricingService,
        carts: CartRepository,
        selector: OrderSelector,
        threads: OrderThreads,
        publisher: EventPublisher,
    ) -> None:
        self._checkout = checkout
        self._pricing = pricing
        self._carts = carts
        self._selector = selector
        self._threads = threads
        self._publisher = publisher

    def quote(
        self,
        actor: Actor,
        lines: Sequence[OrderLineInput],
        *,
        city: str | None = None,
        coupon_code: str | None = None,
    ) -> QuoteView:
        context = PricingContext(city=city, coupon_code=coupon_code, user_id=actor.user_id)
        return self._pricing.price(lines, context).view

    def place(self, actor: Actor, command: PlaceOrder) -> OrderDetail:
        client_id = _user_id(actor)
        with transaction.atomic():
            order = self._checkout.place(client_id, command)
            self._threads.open_for_order(order)
            if cart := self._carts.for_user(client_id):
                self._carts.clear(cart)
            self._publisher.publish(
                OrderPlaced(
                    order_id=order.pk,
                    number=order.number,
                    client_id=client_id,
                    total=order.total,
                    actor_id=client_id,
                )
            )
        return self._with_thread(self._selector.client_detail(client_id, order.number))

    def _with_thread(self, detail: OrderDetail) -> OrderDetail:
        return replace(detail, conversation_id=self._threads.thread_for(detail.summary.id))


@logged_facade
class ClientOrderFacade:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        lifecycle: OrderLifecycleService,
        selector: OrderSelector,
        threads: OrderThreads,
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._lifecycle = lifecycle
        self._selector = selector
        self._threads = threads
        self._publisher = publisher

    def page(
        self, actor: Actor, *, status: OrderStatus | None, offset: int, limit: int
    ) -> OrderPage:
        orders, total = self._selector.client_page(
            _user_id(actor), status=status, offset=offset, limit=limit
        )
        return OrderPage(orders, total, {})

    def detail(self, actor: Actor, number: str) -> OrderDetail:
        detail = self._selector.client_detail(_user_id(actor), normalize_order_number(number))
        return self._decorate(actor, detail)

    def cancel(self, actor: Actor, number: str, command: CancelOrder) -> OrderDetail:
        client_id = _user_id(actor)
        with transaction.atomic():
            order = self._orders.for_client(
                client_id, normalize_order_number(number), for_update=True
            )
            if order is None:
                raise OrderNotFound
            _announce(self._publisher, self._lifecycle.cancel(order, actor, command), actor)
        return self.detail(actor, number)

    def track(self, command: TrackOrder) -> TrackingView:
        return self._selector.tracking(normalize_order_number(command.number), command.contact)

    def _decorate(self, actor: Actor, detail: OrderDetail) -> OrderDetail:
        order = _existing(self._orders.get(detail.summary.id))
        return replace(
            detail,
            allowed_transitions=self._lifecycle.allowed(order, actor),
            conversation_id=self._threads.thread_for(order.pk),
        )


@logged_facade
class DispatchFacade:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        lifecycle: OrderLifecycleService,
        selector: OrderSelector,
        resellers: ResellerDirectory,
        threads: OrderThreads,
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._lifecycle = lifecycle
        self._selector = selector
        self._resellers = resellers
        self._threads = threads
        self._publisher = publisher

    def page(self, actor: Actor, filters: OrderFilters, *, offset: int, limit: int) -> OrderPage:
        orders, total, counts = self._selector.backoffice_page(
            actor, filters, offset=offset, limit=limit
        )
        return OrderPage(orders, total, counts)

    def detail(self, actor: Actor, order_id: int) -> OrderDetail:
        detail = self._selector.backoffice_detail(actor, order_id)
        order = _existing(self._orders.get(order_id))
        return replace(
            detail,
            allowed_transitions=self._lifecycle.allowed(order, actor),
            conversation_id=self._threads.thread_for(order_id),
        )

    def assign(self, actor: Actor, order_id: int, command: AssignOrder) -> OrderDetail:
        with transaction.atomic():
            order = self._locked(actor, order_id)
            change = self._lifecycle.assign(order, actor, command)
            self._publisher.publish(
                OrderAssigned(
                    order_id=order.pk,
                    reseller_id=command.reseller_id,
                    previous_reseller_id=change.previous_reseller_id,
                    actor_id=actor.user_id,
                )
            )
            if change.status_change is not None:
                _announce(self._publisher, change.status_change, actor)
        return self.detail(actor, order_id)

    def decline(self, actor: Actor, order_id: int, command: DeclineAssignment) -> None:
        with transaction.atomic():
            order = self._locked(actor, order_id)
            change = self._lifecycle.decline(order, actor, command)
            self._publisher.publish(
                AssignmentDeclined(
                    order_id=order.pk,
                    reseller_id=_user_id(actor),
                    reason=command.reason,
                    actor_id=actor.user_id,
                )
            )
            _announce(self._publisher, change, actor)

    def transition(self, actor: Actor, order_id: int, command: TransitionOrder) -> OrderDetail:
        with transaction.atomic():
            order = self._locked(actor, order_id)
            _announce(self._publisher, self._lifecycle.transition(order, actor, command), actor)
        return self.detail(actor, order_id)

    def assignable(self, search: str | None) -> list[AssignableReseller]:
        resellers = self._resellers.assignable(search)
        workload = self._selector.open_orders_by_reseller(reseller.id for reseller in resellers)
        return [
            AssignableReseller(
                id=reseller.id,
                name=reseller.name,
                availability=reseller.availability or "offline",
                open_orders=workload.get(reseller.id, 0),
            )
            for reseller in resellers
        ]

    def _locked(self, actor: Actor, order_id: int) -> Order:
        order = scoped_orders(actor).select_for_update().filter(pk=order_id).first()
        if order is None:
            raise OrderNotFound
        return order


def _announce(publisher: EventPublisher, change: StatusChange, actor: Actor) -> None:
    publisher.publish(
        OrderStatusChanged(
            order_id=change.order.pk,
            client_id=change.order.client_id,
            reseller_id=change.order.assigned_reseller_id,
            previous_status=change.previous,
            status=change.status,
            actor_id=actor.user_id,
        )
    )


def _existing(order: Order | None) -> Order:
    if order is None:
        raise OrderNotFound
    return order


def _owner(actor: Actor, token: UUID | None, *, city: str | None = None) -> CartOwner:
    if actor.user_id is not None:
        return CartOwner(user_id=actor.user_id, city=city)
    return CartOwner(token=token, city=city)


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class OrderAdjustmentFacade:
    def __init__(self, *, adjustments: AdjustmentService, publisher: EventPublisher) -> None:
        self._adjustments = adjustments
        self._publisher = publisher

    def adjustable(self, actor: Actor, order_id: int, item_id: int) -> AdjustableItem:
        return self._adjustments.adjustable(actor, order_id, item_id)

    def apply(self, actor: Actor, order_id: int, item_id: int, price: Decimal) -> AdjustableItem:
        with transaction.atomic():
            change = self._adjustments.apply(order_id, item_id, price)
            self._publisher.publish(
                OrderRepriced(
                    order_id=order_id,
                    item_id=item_id,
                    previous_price=change.previous_price,
                    price=price,
                    total=change.order.total,
                    actor_id=actor.user_id,
                )
            )
        return self._adjustments.adjustable(Actor.system(), order_id, item_id)


@logged_facade
class PromotionFacade:
    def __init__(
        self,
        *,
        zones: ShippingZoneService,
        coupons: CouponAdminService,
        selector: PromotionSelector,
    ) -> None:
        self._zones = zones
        self._coupons = coupons
        self._selector = selector

    def shipping_zones(self, *, active_only: bool) -> list[ShippingZoneView]:
        return self._selector.zones(active_only=active_only)

    def create_zone(self, fields: ZoneFields) -> ShippingZoneView:
        with transaction.atomic():
            zone = self._zones.create(fields)
        return self._selector.zone(zone.pk)

    def update_zone(self, zone_id: int, changes: ZoneChanges) -> ShippingZoneView:
        with transaction.atomic():
            self._zones.update(zone_id, changes)
        return self._selector.zone(zone_id)

    def delete_zone(self, zone_id: int) -> None:
        with transaction.atomic():
            self._zones.delete(zone_id)

    def coupons(
        self, *, search: str | None, active: bool | None, offset: int, limit: int
    ) -> tuple[list[CouponView], int]:
        return self._selector.coupons(search=search, active=active, offset=offset, limit=limit)

    def coupon(self, coupon_id: int) -> CouponView:
        return self._selector.coupon(coupon_id)

    def create_coupon(self, fields: CouponFields) -> CouponView:
        with transaction.atomic():
            coupon = self._coupons.create(fields)
        return self._selector.coupon(coupon.pk)

    def update_coupon(self, coupon_id: int, changes: CouponChanges) -> CouponView:
        with transaction.atomic():
            self._coupons.update(coupon_id, changes)
        return self._selector.coupon(coupon_id)

    def deactivate_coupon(self, coupon_id: int) -> CouponView:
        with transaction.atomic():
            self._coupons.deactivate(coupon_id)
        return self._selector.coupon(coupon_id)
