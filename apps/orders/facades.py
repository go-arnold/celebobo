from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from django.db import transaction
from django.utils import timezone

from apps.orders.domain.commands import (
    AssignOrder,
    CancelOrder,
    CouponChanges,
    CouponFields,
    DeclineAssignment,
    OrderFilters,
    OrderLineInput,
    PlaceOrder,
    RateReseller,
    RecordAttempt,
    RecordRefund,
    ReturnLine,
    TrackOrder,
    TransitionOrder,
    ZoneChanges,
    ZoneFields,
)
from apps.orders.domain.enums import CancelReason, OrderStatus
from apps.orders.domain.errors import OrderNotFound
from apps.orders.domain.events import (
    AssignmentDeclined,
    DeliveredWithoutCode,
    DeliveryAttemptFailed,
    DeliveryCodeIssued,
    DeliveryCodeLocked,
    OrderAssigned,
    OrderLineReturned,
    OrderPlaced,
    OrderRefunded,
    OrderRepriced,
    OrderStatusChanged,
    RefundDue,
    ResellerRated,
    ShippingFeeAccepted,
)
from apps.orders.domain.numbers import normalize_order_number
from apps.orders.domain.read_models import (
    AdjustableItem,
    AssignableReseller,
    CartView,
    CouponView,
    OrderDetail,
    OrderSummary,
    QuotableOrder,
    QuoteView,
    ShippingZoneView,
    TrackingView,
)
from apps.orders.models import Order
from apps.orders.repositories import CartRepository, OrderRepository
from apps.orders.selectors import OrderSelector, PromotionSelector, scoped_orders
from apps.orders.services.adjustments import AdjustmentService
from apps.orders.services.attempts import DeliveryAttemptService
from apps.orders.services.cart import CartOwner, CartService
from apps.orders.services.checkout import CheckoutService
from apps.orders.services.contracts import OrderThreads, ResellerDirectory, Wallet
from apps.orders.services.lifecycle import Handover, OrderLifecycleService, StatusChange
from apps.orders.services.pricing import PricingContext, PricingService
from apps.orders.services.promotions import CouponAdminService, ShippingZoneService
from apps.orders.services.ratings import RatingService
from apps.orders.services.refunds import RefundService
from apps.orders.services.returns import LineReturnService
from apps.orders.services.shipping_quotes import ShippingQuoteService
from core.domain.actor import Actor
from core.domain.errors import DomainError, Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade

logger = structlog.get_logger(__name__)


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
        wallet: Wallet,
        publisher: EventPublisher,
    ) -> None:
        self._wallet = wallet
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
        use_cashback: bool = False,
        pickup: bool = False,
    ) -> QuoteView:
        context = PricingContext(
            city=city,
            coupon_code=coupon_code,
            user_id=actor.user_id,
            use_cashback=use_cashback,
            pickup=pickup,
        )
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
        return replace(
            detail,
            conversation_id=self._threads.thread_for(detail.summary.id),
            cashback_earned=self._wallet.earned(detail.summary.id),
        )


@logged_facade
class ClientOrderFacade:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        lifecycle: OrderLifecycleService,
        selector: OrderSelector,
        threads: OrderThreads,
        wallet: Wallet,
        publisher: EventPublisher,
    ) -> None:
        self._orders = orders
        self._lifecycle = lifecycle
        self._selector = selector
        self._threads = threads
        self._wallet = wallet
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

    # once delivered, the client rates the reseller who handled the order (once)
    def rate(self, actor: Actor, number: str, command: RateReseller) -> OrderDetail:
        client_id = _user_id(actor)
        with transaction.atomic():
            order = self._orders.for_client(
                client_id, normalize_order_number(number), for_update=True
            )
            if order is None:
                raise OrderNotFound
            rating = RatingService().rate(order, command)
            self._publisher.publish(
                ResellerRated(
                    order_id=order.pk,
                    reseller_id=rating.reseller_id,
                    score=rating.score,
                    actor_id=client_id,
                )
            )
        return self.detail(actor, number)

    def track(self, command: TrackOrder) -> TrackingView:
        return self._selector.tracking(normalize_order_number(command.number), command.contact)

    def _decorate(self, actor: Actor, detail: OrderDetail) -> OrderDetail:
        order = _existing(self._orders.get(detail.summary.id))
        return replace(
            detail,
            allowed_transitions=self._lifecycle.allowed(order, actor),
            conversation_id=self._threads.thread_for(order.pk),
            cashback_earned=self._wallet.earned(order.pk),
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
        wallet: Wallet,
        returns: LineReturnService,
        refunds: RefundService,
        attempts: DeliveryAttemptService,
        publisher: EventPublisher,
    ) -> None:
        self._attempts = attempts
        self._refunds = refunds
        self._orders = orders
        self._lifecycle = lifecycle
        self._selector = selector
        self._resellers = resellers
        self._threads = threads
        self._wallet = wallet
        self._publisher = publisher
        self._returns = returns

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
            cashback_earned=self._wallet.earned(order_id),
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
        refused: DomainError | None = None
        with transaction.atomic():
            order = self._locked(actor, order_id)
            handover = (
                self._lifecycle.handover(order, actor, command)
                if command.to is OrderStatus.DELIVERED
                and command.to in self._lifecycle.allowed(order, actor)
                else Handover()
            )
            if handover.locked_now:
                self._publisher.publish(
                    DeliveryCodeLocked(order_id=order.pk, actor_id=actor.user_id)
                )
            if handover.error is not None:
                # the wrong attempt stays counted: refuse only once this transaction commits
                refused = handover.error
            else:
                if command.to is OrderStatus.DELIVERED:
                    command = replace(command, note=_handover_note(handover))
                _announce(self._publisher, self._lifecycle.transition(order, actor, command), actor)
                if handover.without_code is not None:
                    self._publisher.publish(
                        DeliveredWithoutCode(
                            order_id=order.pk, reason=handover.without_code, actor_id=actor.user_id
                        )
                    )
        if refused is not None:
            raise refused
        return self.detail(actor, order_id)

    # the reseller could not deliver: on the second working day of failures the order is cancelled
    def record_attempt(self, actor: Actor, order_id: int, command: RecordAttempt) -> OrderDetail:
        with transaction.atomic():
            order = self._locked(actor, order_id)
            outcome = self._attempts.record(order, actor, command)
            self._publisher.publish(
                DeliveryAttemptFailed(
                    order_id=order.pk,
                    reason=command.reason.value,
                    days=outcome.days,
                    actor_id=actor.user_id,
                )
            )
            if outcome.cancellation is not None:
                _announce(self._publisher, outcome.cancellation, Actor.system())
        return self.detail(actor, order_id)

    # a paid order was cancelled: staff record that the money went back to the client
    def refund(self, actor: Actor, order_id: int, command: RecordRefund) -> OrderDetail:
        with transaction.atomic():
            order = self._refunds.record(self._locked(actor, order_id), actor, command)
            self._publisher.publish(
                OrderRefunded(order_id=order.pk, amount=order.refund_due, actor_id=actor.user_id)
            )
        return self.detail(actor, order_id)

    # sales and cashback follow the return in this transaction (transactional handlers); once
    # every unit is back the order itself becomes returned
    def return_line(
        self, actor: Actor, order_id: int, item_id: int, command: ReturnLine
    ) -> OrderDetail:
        with transaction.atomic():
            order = self._locked(actor, order_id)
            result = self._returns.return_line(order, item_id, actor, command)
            self._publisher.publish(
                OrderLineReturned(
                    order_id=order.pk,
                    item_id=result.item.pk,
                    quantity=command.quantity,
                    amount_paid=result.share.paid,
                    discount=result.share.discount,
                    cashback=result.share.cashback,
                    actor_id=actor.user_id,
                )
            )
            if result.order_fully_returned:
                change = self._lifecycle.transition(
                    order,
                    actor,
                    TransitionOrder(to=OrderStatus.RETURNED, note="Tous les articles retournés"),
                )
                _announce(self._publisher, change, actor)
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


@logged_facade
class OrderExpiryFacade:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        lifecycle: OrderLifecycleService,
        publisher: EventPublisher,
        ttl_hours: int,
        clock: Callable[[], datetime] = timezone.now,
    ) -> None:
        self._orders = orders
        self._lifecycle = lifecycle
        self._publisher = publisher
        self._ttl_hours = ttl_hours
        self._clock = clock

    # one transaction per order: a failure is logged and the next run retries it
    def expire_stale(self) -> int:
        cutoff = self._clock() - timedelta(hours=self._ttl_hours)
        actor = Actor.system()
        expired = 0
        for order_id in self._orders.stale_pending(cutoff):
            try:
                with transaction.atomic():
                    order = self._orders.stale(order_id, cutoff)
                    if order is None:
                        continue
                    change = self._lifecycle.expire(order, actor, hours=self._ttl_hours)
                    _announce(self._publisher, change, actor)
            except Exception:
                logger.exception("orders.expiry_failed", order_id=order_id)
                continue
            expired += 1
        return expired


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
    if change.code_issued:
        publisher.publish(DeliveryCodeIssued(order_id=change.order.pk, actor_id=actor.user_id))
    if change.status is OrderStatus.CANCELLED and change.order.refund_due > 0:
        publisher.publish(
            RefundDue(
                order_id=change.order.pk,
                amount=change.order.refund_due,
                delivery_failed=change.order.cancel_reason == CancelReason.DELIVERY_FAILED,
                actor_id=actor.user_id,
            )
        )


def _handover_note(handover: Handover) -> str:
    if handover.without_code is not None:
        return f"Livraison confirmée sans code par un responsable : {handover.without_code}"[:500]
    return "Remise confirmée avec le code de livraison du client"


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
class ShippingQuoteFacade:
    def __init__(self, *, quotes: ShippingQuoteService, publisher: EventPublisher) -> None:
        self._quotes = quotes
        self._publisher = publisher

    def quotable(self, actor: Actor, order_id: int) -> QuotableOrder:
        return self._quotes.quotable(actor, order_id)

    def accept(self, actor: Actor, order_id: int, fee: Decimal, delivery_estimate: str) -> None:
        with transaction.atomic():
            order = self._quotes.accept(actor, order_id, fee, delivery_estimate)
            self._publisher.publish(
                ShippingFeeAccepted(
                    order_id=order.pk, fee=fee, total=order.total, actor_id=actor.user_id
                )
            )


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

    def reorder_zones(self, ids: Sequence[int]) -> list[ShippingZoneView]:
        with transaction.atomic():
            self._zones.reorder(ids)
        return self._selector.zones(active_only=False)

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
