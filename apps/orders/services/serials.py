from collections.abc import Callable, Sequence
from datetime import datetime

from django.db.models import F

from apps.orders.domain import serials
from apps.orders.domain.commands import RecordSerials
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import (
    InvalidSerialNumber,
    NotAssignedToYou,
    OrderItemNotFound,
    SerialNumberAlreadySold,
    SerialNumbersMissing,
    SerialNumbersNotEditable,
    TooManySerialNumbers,
)
from apps.orders.models import Order, OrderItem, OrderItemSerial
from core.domain.actor import Actor

# an order that leaves for delivery, or is handed over, carries the serial of each unit
LEAVING = frozenset({OrderStatus.SHIPPING, OrderStatus.DELIVERED})
# a unit of a cancelled or returned order is back in stock: its serial can be sold again
RELEASED = (OrderStatus.CANCELLED.value, OrderStatus.RETURNED.value)


# before shipping or delivery: every unit of a line that needs it has its number
def ensure_complete(order: Order, status: OrderStatus) -> None:
    if status not in LEAVING:
        return
    missing = [
        {"item_id": item.pk, "name": item.product_name, "missing": item.quantity - count}
        for item in OrderItem.objects.filter(order=order, serial_required=True)
        if (count := item.serials.count()) < item.quantity
    ]
    if missing:
        raise SerialNumbersMissing(missing)


class SerialNumberService:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    # the assigned reseller or staff, before the delivery; afterwards only staff correct them
    def record(
        self, order: Order, actor: Actor, item_id: int, command: RecordSerials
    ) -> list[OrderItemSerial]:
        if not (actor.is_staff or actor.owns(order.assigned_reseller_id)):
            raise NotAssignedToYou
        status = order.order_status
        if status in (OrderStatus.CANCELLED, OrderStatus.RETURNED) or (
            status is OrderStatus.DELIVERED and not actor.is_staff
        ):
            raise SerialNumbersNotEditable
        item = OrderItem.objects.filter(order=order, pk=item_id).first()
        if item is None:
            raise OrderItemNotFound
        cleaned = self._clean(command.serials)
        if len(cleaned) > item.quantity:
            raise TooManySerialNumbers
        self._ensure_free(order, cleaned)
        OrderItemSerial.objects.filter(item=item).exclude(serial__in=cleaned).delete()
        kept = set(OrderItemSerial.objects.filter(item=item).values_list("serial", flat=True))
        now = self._clock()
        OrderItemSerial.objects.bulk_create(
            OrderItemSerial(item=item, serial=serial, recorded_by_id=actor.user_id, recorded_at=now)
            for serial in cleaned
            if serial not in kept
        )
        return list(OrderItemSerial.objects.filter(item=item))

    @staticmethod
    def _clean(raw: Sequence[str]) -> list[str]:
        cleaned: list[str] = []
        errors: list[str] = []
        for value in raw:
            serial = serials.normalize(value)
            if not serial:
                continue
            if (why := serials.problem(serial)) is not None:
                errors.append(f"{serial} : {why}")
            elif serial not in cleaned:
                cleaned.append(serial)
        if errors:
            raise InvalidSerialNumber(errors={"serials": errors})
        return cleaned

    # one unit cannot be on two orders still running (a typo, or the same phone sold twice)
    @staticmethod
    def _ensure_free(order: Order, cleaned: list[str]) -> None:
        taken = (
            OrderItemSerial.objects.filter(serial__in=cleaned)
            .exclude(item__order=order)
            .exclude(item__order__status__in=RELEASED)
            .exclude(item__returned_quantity=F("item__quantity"))
            .values_list("serial", "item__order__number")
            .first()
        )
        if taken is not None:
            raise SerialNumberAlreadySold(*taken)
