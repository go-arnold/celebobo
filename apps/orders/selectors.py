from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal

from django.db.models import Avg, Count, Q, QuerySet, Sum
from django.utils import timezone

from apps.orders.domain.commands import OrderFilters
from apps.orders.domain.enums import (
    FINAL_STATUSES,
    RATABLE_STATUSES,
    AttemptReason,
    DeliveryMethod,
    OrderStatus,
    PaymentMethod,
)
from apps.orders.domain.errors import CouponNotFound, OrderNotFound, ShippingZoneNotFound
from apps.orders.domain.pricing import ZonePricing
from apps.orders.domain.read_models import (
    AddressSnapshot,
    AttemptView,
    ClientOrderTotals,
    ConvertibleItem,
    ConvertibleOrder,
    CouponView,
    OrderDelivery,
    OrderDetail,
    OrderLineView,
    OrderRef,
    OrderSummary,
    PersonBrief,
    RatingSummary,
    RatingView,
    ResellerRatingRow,
    ShippingZoneView,
    StatusEntry,
    TrackedItem,
    TrackedStatus,
    TrackingView,
)
from apps.orders.models import (
    Coupon,
    CouponRedemption,
    Order,
    OrderItem,
    OrderRating,
    OrderStatusEvent,
    ShippingZone,
)
from core.domain.actor import Actor


def scoped_orders(actor: Actor) -> QuerySet[Order]:
    orders = Order.objects.all()
    if actor.is_staff:
        return orders
    if actor.is_backoffice:
        return orders.filter(assigned_reseller_id=actor.user_id)
    return orders.none()


class OrderSelector:
    def client_page(
        self, client_id: int, *, status: OrderStatus | None, offset: int, limit: int
    ) -> tuple[list[OrderSummary], int]:
        orders = Order.objects.filter(client_id=client_id)
        if status is not None:
            orders = orders.filter(status=status.value)
        return self._page(orders, offset, limit)

    def backoffice_page(
        self, actor: Actor, filters: OrderFilters, *, offset: int, limit: int
    ) -> tuple[list[OrderSummary], int, dict[str, int]]:
        staff = actor.is_staff
        scoped = _filtered(scoped_orders(actor), filters, include_status=False, staff=staff)
        counts = dict(
            scoped.values_list("status").annotate(total=Count("pk")).values_list("status", "total")
        )
        counts = {status.value: counts.get(status.value, 0) for status in OrderStatus}
        counts["unassigned"] = scoped.filter(
            assigned_reseller__isnull=True, status=OrderStatus.PENDING.value
        ).count()
        counts["refund_pending"] = scoped.filter(_REFUND_PENDING).count()
        summaries, total = self._page(
            _filtered(scoped, filters, include_status=True, staff=staff),
            offset,
            limit,
            staff=staff,
        )
        return summaries, total, counts

    def client_detail(self, client_id: int, number: str) -> OrderDetail:
        return self._detail(Order.objects.filter(client_id=client_id, number=number), staff=True)

    def backoffice_detail(self, actor: Actor, order_id: int) -> OrderDetail:
        return self._detail(scoped_orders(actor).filter(pk=order_id), staff=actor.is_staff)

    def tracking(self, number: str, contact: str) -> TrackingView:
        normalized = contact.strip().lower()
        order = (
            Order.objects.filter(number=number)
            .filter(Q(client__email__iexact=normalized) | Q(phone=contact.strip()))
            .prefetch_related("items", "history")
            .first()
        )
        if order is None:
            raise OrderNotFound
        return TrackingView(
            number=order.number,
            status=order.order_status,
            created_at=order.created_at,
            total=order.total,
            items=tuple(
                TrackedItem(
                    name=item.product_name, variant_label=item.variant_label, quantity=item.quantity
                )
                for item in order.items.all()
            ),
            history=tuple(
                TrackedStatus(status=OrderStatus(event.to_status), at=event.created_at)
                for event in order.history.all()
            ),
        )

    def open_page(self, actor: Actor, *, limit: int) -> tuple[list[OrderSummary], int]:
        orders = scoped_orders(actor).exclude(
            status__in=[status.value for status in FINAL_STATUSES]
        )
        return self._page(orders, 0, limit, staff=actor.is_staff)

    def open_orders_by_reseller(self, reseller_ids: Iterable[int]) -> dict[int, int]:
        open_statuses = [status.value for status in OrderStatus if status.is_open]
        return dict(
            Order.objects.filter(
                assigned_reseller_id__in=list(reseller_ids), status__in=open_statuses
            )
            .values_list("assigned_reseller_id")
            .annotate(total=Count("pk"))
            .values_list("assigned_reseller_id", "total")
        )

    # staff=False: the viewer is a reseller, who never gets the client's e-mail (privacy policy §4)
    def _page(
        self, orders: QuerySet[Order], offset: int, limit: int, *, staff: bool = True
    ) -> tuple[list[OrderSummary], int]:
        page = (
            orders.select_related("client", "assigned_reseller")
            .annotate(items_count=Count("items"))
            .order_by("-created_at", "-pk")[offset : offset + limit]
        )
        previews = _previews(order.pk for order in page)
        summaries = [_summary(order, previews.get(order.pk), staff=staff) for order in page]
        return summaries, orders.count()

    def _detail(self, orders: QuerySet[Order], *, staff: bool) -> OrderDetail:
        order = (
            orders.select_related("client", "assigned_reseller", "rating")
            .prefetch_related("items__returns", "history__actor", "delivery_attempts")
            .annotate(items_count=Count("items", distinct=True))
            .first()
        )
        if order is None:
            raise OrderNotFound
        items = list(order.items.all())
        client = order.client
        reseller = order.assigned_reseller
        return OrderDetail(
            summary=_summary(order, items[0] if items else None, staff=staff),
            items=tuple(_line(item) for item in items),
            address=AddressSnapshot(
                recipient=order.recipient,
                phone=order.phone,
                line1=order.line1,
                quarter=order.quarter,
                city=order.city,
                country=order.country,
            ),
            payment_method=PaymentMethod(order.payment_method),
            note=order.note,
            subtotal=order.subtotal,
            discount=order.discount,
            coupon_code=order.coupon_code,
            points=order.points,
            shipping_zone=order.shipping_zone,
            shipping_fee=order.shipping_fee,
            delivery_method=DeliveryMethod(order.delivery_method),
            pickup_address=order.pickup_address,
            delivery_estimate=order.delivery_estimate,
            awaiting_shipping_quote=order.awaiting_shipping_quote,
            refund_due=order.refund_due,
            refunded_at=order.refunded_at,
            refund_note=order.refund_note,
            delivery_code=order.delivery_code,
            delivery_code_attempts=order.delivery_code_attempts,
            delivery_code_locked=order.delivery_code_locked_at is not None,
            rating=_rating(order),
            delivery_attempts=tuple(
                AttemptView(
                    at=attempt.created_at,
                    reason=attempt.reason,
                    reason_label=AttemptReason(attempt.reason).label,
                    note=attempt.note,
                )
                for attempt in order.delivery_attempts.all()
            ),
            can_rate=order.order_status in RATABLE_STATUSES
            and order.assigned_reseller_id is not None
            and getattr(order, "rating", None) is None,
            cancel_reason=order.cancel_reason,
            history=tuple(
                StatusEntry(
                    status=OrderStatus(event.to_status),
                    at=event.created_at,
                    actor_role=event.actor_role,
                    actor_name=_display_name(event.actor) if event.actor else None,
                    note=event.note,
                )
                for event in order.history.all()
            ),
            allowed_transitions=(),
            client=PersonBrief(
                id=client.pk,
                name=_client_name(order, staff=staff),
                email=client.email if staff else None,
                phone=getattr(client, "phone_number", None),
            ),
            reseller=(
                PersonBrief(
                    id=reseller.pk,
                    name=_display_name(reseller),
                    email=reseller.email,
                    availability=getattr(reseller, "availability", None),
                )
                if reseller
                else None
            ),
            conversation_id=None,
        )


_REFUND_PENDING = Q(refund_due__gt=0, refunded_at__isnull=True)


def _filtered(
    orders: QuerySet[Order], filters: OrderFilters, *, include_status: bool, staff: bool
) -> QuerySet[Order]:
    if include_status and filters.unassigned:
        orders = orders.filter(assigned_reseller__isnull=True, status=OrderStatus.PENDING.value)
    if include_status and filters.refund_pending:
        orders = orders.filter(_REFUND_PENDING)
    if include_status and filters.status is not None:
        orders = orders.filter(status=filters.status.value)
    if filters.reseller_id is not None:
        orders = orders.filter(assigned_reseller_id=filters.reseller_id)
    if filters.payment_method is not None:
        orders = orders.filter(payment_method=filters.payment_method.value)
    if filters.date_from is not None:
        orders = orders.filter(created_at__gte=_start_of(filters.date_from))
    if filters.date_to is not None:
        orders = orders.filter(created_at__lte=_end_of(filters.date_to))
    if filters.search:
        term = filters.search.strip()
        matches = (
            Q(number__icontains=term)
            | Q(client__first_name__icontains=term)
            | Q(client__last_name__icontains=term)
            | Q(recipient__icontains=term)
            | Q(phone__icontains=term)
        )
        if staff:
            # searching by e-mail would let a reseller confirm a client's address
            matches |= Q(client__email__icontains=term)
        orders = orders.filter(matches)
    return orders


def _previews(order_ids: Iterable[int]) -> dict[int, OrderItem]:
    previews: dict[int, OrderItem] = {}
    for item in OrderItem.objects.filter(order_id__in=list(order_ids)).order_by("order_id", "pk"):
        previews.setdefault(item.order_id, item)
    return previews


def _summary(order: Order, preview: OrderItem | None, *, staff: bool) -> OrderSummary:
    reseller = order.assigned_reseller
    return OrderSummary(
        id=order.pk,
        number=order.number,
        status=order.order_status,
        created_at=order.created_at,
        total=order.total,
        items_count=getattr(order, "items_count", 0),
        preview_name=preview.product_name if preview else "",
        preview_image=preview.product_image if preview else "",
        client_name=_client_name(order, staff=staff),
        reseller_name=_display_name(reseller) if reseller else None,
        refund_status=_refund_status(order),
    )


def _rating(order: Order) -> RatingView | None:
    rating = getattr(order, "rating", None)
    if rating is None:
        return None
    return RatingView(score=rating.score, comment=rating.comment, created_at=rating.created_at)


# the resellers directory shows each reseller's average and number of ratings
def rating_summaries(reseller_ids: Iterable[int]) -> dict[int, RatingSummary]:
    ids = list(reseller_ids)
    rows = (
        OrderRating.objects.filter(reseller_id__in=ids)
        .values("reseller_id")
        .annotate(average=Avg("score"), count=Count("pk"))
    )
    found = {
        row["reseller_id"]: RatingSummary(
            average=Decimal(str(row["average"])).quantize(Decimal("0.1")), count=row["count"]
        )
        for row in rows
    }
    return {pk: found.get(pk, RatingSummary(average=None, count=0)) for pk in ids}


def reseller_ratings(
    reseller_id: int, *, offset: int, limit: int
) -> tuple[list[ResellerRatingRow], int]:
    ratings = OrderRating.objects.filter(reseller_id=reseller_id).select_related("order", "client")
    rows = [
        ResellerRatingRow(
            order_number=rating.order.number,
            client_name=rating.client.first_name or "Client",
            score=rating.score,
            comment=rating.comment,
            created_at=rating.created_at,
        )
        for rating in ratings[offset : offset + limit]
    ]
    return rows, ratings.count()


def _refund_status(order: Order) -> str | None:
    if order.refund_due <= 0:
        return None
    return "done" if order.refunded_at is not None else "due"


def _line(item: OrderItem) -> OrderLineView:
    return OrderLineView(
        id=item.pk,
        product_id=item.product_id,
        variant_id=item.variant_id,
        name=item.product_name,
        variant_label=item.variant_label,
        image=item.product_image,
        sku=item.sku,
        quantity=item.quantity,
        unit_price=item.unit_price,
        total=item.total,
        discount=item.discount,
        points=item.points,
        amount_paid=item.amount_paid,
        returned_quantity=item.returned_quantity,
        returned_amount=sum((entry.amount_paid for entry in item.returns.all()), Decimal(0)),
    )


# without a name on the account, staff see the e-mail and resellers the delivery recipient
def _client_name(order: Order, *, staff: bool) -> str:
    name = _display_name(order.client)
    if staff or name != order.client.email:
        return name
    return order.recipient


def _display_name(user: object) -> str:
    first = getattr(user, "first_name", "")
    last = getattr(user, "last_name", "")
    return f"{first} {last}".strip() or str(getattr(user, "email", ""))


def _start_of(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _end_of(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max))


def order_ref(order_id: int) -> OrderRef:
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        raise OrderNotFound
    return OrderRef(
        id=order.pk,
        number=order.number,
        client_id=order.client_id,
        reseller_id=order.assigned_reseller_id,
        status=order.order_status,
        total=order.total,
    )


def order_delivery(order_id: int) -> OrderDelivery | None:
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return None
    delivered = (
        OrderStatusEvent.objects.filter(order=order, to_status=OrderStatus.DELIVERED.value)
        .order_by("-created_at", "-pk")
        .values_list("created_at", flat=True)
        .first()
    )
    return OrderDelivery(
        id=order.pk,
        number=order.number,
        status=order.order_status,
        reseller_id=order.assigned_reseller_id,
        delivery_method=DeliveryMethod(order.delivery_method),
        shipping_fee=order.shipping_fee,
        delivered_at=delivered,
    )


# for the client's notification only: never exposed to the back-office
def delivery_code(order_id: int) -> str:
    code = Order.objects.filter(pk=order_id).values_list("delivery_code", flat=True).first()
    if code is None:
        raise OrderNotFound
    return code


CONVERTIBLE_STATUSES = (OrderStatus.DELIVERED,)


def convertible_orders(
    actor: Actor, search: str | None, *, limit: int = 20
) -> list[ConvertibleOrder]:
    orders = scoped_orders(actor).filter(
        status__in=[status.value for status in CONVERTIBLE_STATUSES]
    )
    if search:
        orders = _filtered(
            orders, OrderFilters(search=search), include_status=False, staff=actor.is_staff
        )
    return [
        _convertible(order, staff=actor.is_staff)
        for order in orders.select_related("client")
        .prefetch_related("items")
        .order_by("-created_at", "-pk")[:limit]
    ]


def convertible_order(actor: Actor, order_id: int) -> ConvertibleOrder:
    order = (
        scoped_orders(actor)
        .select_related("client")
        .prefetch_related("items")
        .filter(pk=order_id)
        .first()
    )
    if order is None:
        raise OrderNotFound
    return _convertible(order, staff=actor.is_staff)


def _convertible(order: Order, *, staff: bool) -> ConvertibleOrder:
    return ConvertibleOrder(
        id=order.pk,
        number=order.number,
        status=order.order_status,
        client_id=order.client_id,
        client_name=_client_name(order, staff=staff),
        reseller_id=order.assigned_reseller_id,
        payment_method=PaymentMethod(order.payment_method),
        total=order.total,
        created_at=order.created_at,
        items=tuple(
            ConvertibleItem(
                id=item.pk,
                product_id=item.product_id,
                variant_id=item.variant_id,
                name=item.product_name,
                variant_label=item.variant_label,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            for item in order.items.all()
        ),
    )


UNCOUNTED_STATUSES = (OrderStatus.CANCELLED.value, OrderStatus.RETURNED.value)


def client_order_totals(client_ids: Iterable[int]) -> dict[int, ClientOrderTotals]:
    rows = (
        Order.objects.filter(client_id__in=list(client_ids))
        .exclude(status__in=UNCOUNTED_STATUSES)
        .values("client_id")
        .annotate(count=Count("pk"), total=Sum("total"))
    )
    return {
        row["client_id"]: ClientOrderTotals(count=row["count"], total=Decimal(row["total"]))
        for row in rows
    }


class PromotionSelector:
    def zones(self, *, active_only: bool) -> list[ShippingZoneView]:
        zones = ShippingZone.objects.all()
        if active_only:
            zones = zones.filter(is_active=True)
        return [to_zone_view(zone) for zone in zones]

    def zone(self, zone_id: int) -> ShippingZoneView:
        zone = ShippingZone.objects.filter(pk=zone_id).first()
        if zone is None:
            raise ShippingZoneNotFound
        return to_zone_view(zone)

    def coupons(
        self, *, search: str | None, active: bool | None, offset: int, limit: int
    ) -> tuple[list[CouponView], int]:
        coupons = Coupon.objects.all()
        if search:
            coupons = coupons.filter(
                Q(code__icontains=search.strip()) | Q(description__icontains=search.strip())
            )
        if active is not None:
            coupons = coupons.filter(is_active=active)
        page = list(coupons[offset : offset + limit])
        usage = _coupon_usage(coupon.pk for coupon in page)
        return [to_coupon_view(coupon, usage.get(coupon.pk)) for coupon in page], coupons.count()

    def coupon(self, coupon_id: int) -> CouponView:
        coupon = Coupon.objects.filter(pk=coupon_id).first()
        if coupon is None:
            raise CouponNotFound
        return to_coupon_view(coupon, _coupon_usage([coupon.pk]).get(coupon.pk))


def to_zone_view(zone: ShippingZone) -> ShippingZoneView:
    return ShippingZoneView(
        id=zone.pk,
        name=zone.name,
        cities=tuple(zone.cities),
        fee=zone.fee,
        free_threshold=zone.free_threshold,
        delivery_estimate=zone.delivery_estimate,
        is_default=zone.is_default,
        is_active=zone.is_active,
        position=zone.position,
        pricing=ZonePricing(zone.pricing),
        pickup_address=zone.pickup_address,
    )


def to_coupon_view(coupon: Coupon, usage: tuple[int, Decimal] | None) -> CouponView:
    uses, amount = usage or (0, Decimal("0.00"))
    return CouponView(
        id=coupon.pk,
        code=coupon.code,
        description=coupon.description,
        kind=coupon.kind,
        value=coupon.value,
        max_discount=coupon.max_discount,
        min_subtotal=coupon.min_subtotal,
        free_shipping=coupon.free_shipping,
        starts_at=coupon.starts_at,
        ends_at=coupon.ends_at,
        usage_limit=coupon.usage_limit,
        per_user_limit=coupon.per_user_limit,
        is_active=coupon.is_active,
        uses=uses,
        discount_total=amount,
        created_at=coupon.created_at,
    )


def _coupon_usage(coupon_ids: Iterable[int]) -> dict[int, tuple[int, Decimal]]:
    rows = (
        CouponRedemption.objects.filter(coupon_id__in=list(coupon_ids))
        .exclude(order__status=OrderStatus.CANCELLED.value)
        .values("coupon_id")
        .annotate(uses=Count("pk"), amount=Sum("amount"))
    )
    return {row["coupon_id"]: (int(row["uses"]), Decimal(row["amount"] or 0)) for row in rows}
