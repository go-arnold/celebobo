from collections.abc import Iterable
from datetime import date, datetime, time

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.orders.domain.commands import OrderFilters
from apps.orders.domain.enums import OrderStatus, PaymentMethod
from apps.orders.domain.errors import OrderNotFound
from apps.orders.domain.read_models import (
    AddressSnapshot,
    ConvertibleItem,
    ConvertibleOrder,
    OrderDetail,
    OrderLineView,
    OrderRef,
    OrderSummary,
    PersonBrief,
    StatusEntry,
    TrackedItem,
    TrackedStatus,
    TrackingView,
)
from apps.orders.models import Order, OrderItem
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
        scoped = _filtered(scoped_orders(actor), filters, include_status=False)
        counts = dict(
            scoped.values_list("status").annotate(total=Count("pk")).values_list("status", "total")
        )
        counts = {status.value: counts.get(status.value, 0) for status in OrderStatus}
        counts["unassigned"] = scoped.filter(
            assigned_reseller__isnull=True, status=OrderStatus.PENDING.value
        ).count()
        summaries, total = self._page(
            _filtered(scoped, filters, include_status=True), offset, limit
        )
        return summaries, total, counts

    def client_detail(self, client_id: int, number: str) -> OrderDetail:
        return self._detail(Order.objects.filter(client_id=client_id, number=number))

    def backoffice_detail(self, actor: Actor, order_id: int) -> OrderDetail:
        return self._detail(scoped_orders(actor).filter(pk=order_id))

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

    def _page(
        self, orders: QuerySet[Order], offset: int, limit: int
    ) -> tuple[list[OrderSummary], int]:
        page = (
            orders.select_related("client", "assigned_reseller")
            .annotate(items_count=Count("items"))
            .order_by("-created_at", "-pk")[offset : offset + limit]
        )
        previews = _previews(order.pk for order in page)
        return [_summary(order, previews.get(order.pk)) for order in page], orders.count()

    def _detail(self, orders: QuerySet[Order]) -> OrderDetail:
        order = (
            orders.select_related("client", "assigned_reseller")
            .prefetch_related("items", "history__actor")
            .annotate(items_count=Count("items", distinct=True))
            .first()
        )
        if order is None:
            raise OrderNotFound
        items = list(order.items.all())
        client = order.client
        reseller = order.assigned_reseller
        return OrderDetail(
            summary=_summary(order, items[0] if items else None),
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
            shipping_fee=order.shipping_fee,
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
                name=_display_name(client),
                email=client.email,
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


def _filtered(
    orders: QuerySet[Order], filters: OrderFilters, *, include_status: bool
) -> QuerySet[Order]:
    if include_status and filters.unassigned:
        orders = orders.filter(assigned_reseller__isnull=True, status=OrderStatus.PENDING.value)
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
        orders = orders.filter(
            Q(number__icontains=term)
            | Q(client__email__icontains=term)
            | Q(client__first_name__icontains=term)
            | Q(client__last_name__icontains=term)
            | Q(recipient__icontains=term)
            | Q(phone__icontains=term)
        )
    return orders


def _previews(order_ids: Iterable[int]) -> dict[int, OrderItem]:
    previews: dict[int, OrderItem] = {}
    for item in OrderItem.objects.filter(order_id__in=list(order_ids)).order_by("order_id", "pk"):
        previews.setdefault(item.order_id, item)
    return previews


def _summary(order: Order, preview: OrderItem | None) -> OrderSummary:
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
        client_name=_display_name(order.client),
        reseller_name=_display_name(reseller) if reseller else None,
    )


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
        total=item.unit_price * item.quantity,
    )


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


CONVERTIBLE_STATUSES = (
    OrderStatus.CONFIRMED,
    OrderStatus.PAID,
    OrderStatus.SHIPPING,
    OrderStatus.DELIVERED,
)


def convertible_orders(
    actor: Actor, search: str | None, *, limit: int = 20
) -> list[ConvertibleOrder]:
    orders = scoped_orders(actor).filter(
        status__in=[status.value for status in CONVERTIBLE_STATUSES]
    )
    if search:
        orders = _filtered(orders, OrderFilters(search=search), include_status=False)
    return [
        _convertible(order)
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
    return _convertible(order)


def _convertible(order: Order) -> ConvertibleOrder:
    return ConvertibleOrder(
        id=order.pk,
        number=order.number,
        status=order.order_status,
        client_id=order.client_id,
        client_name=_display_name(order.client),
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
