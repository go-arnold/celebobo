from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPING = "shipping"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"

    @property
    def label(self) -> str:
        return {
            "pending": "En attente",
            "assigned": "Assignée",
            "confirmed": "Confirmée",
            "paid": "Payée",
            "shipping": "En livraison",
            "delivered": "Livrée",
            "cancelled": "Annulée",
            "returned": "Retournée",
        }[self.value]

    @property
    def is_final(self) -> bool:
        return self in FINAL_STATUSES

    @property
    def is_open(self) -> bool:
        return not self.is_final


FINAL_STATUSES = frozenset({OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED})

# the client may cancel, free of charge, until the order leaves for delivery
CLIENT_CANCELLABLE = frozenset(
    {OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.CONFIRMED, OrderStatus.PAID}
)
# the client has paid: cancelling from here means giving the money back
PAID_STATUSES = frozenset({OrderStatus.PAID, OrderStatus.SHIPPING})

FULFILMENT_FLOW = (
    OrderStatus.PENDING,
    OrderStatus.ASSIGNED,
    OrderStatus.CONFIRMED,
    OrderStatus.PAID,
    OrderStatus.SHIPPING,
    OrderStatus.DELIVERED,
)


class DeliveryMethod(StrEnum):
    DELIVERY = "delivery"
    PICKUP = "pickup"

    @property
    def label(self) -> str:
        return {"delivery": "Livraison", "pickup": "Retrait sur place"}[self.value]


class PaymentMethod(StrEnum):
    ORANGE_MONEY = "orange_money"
    AIRTEL_MONEY = "airtel_money"
    MPESA = "mpesa"
    CASH = "cash"

    @property
    def label(self) -> str:
        return {
            "orange_money": "Orange Money",
            "airtel_money": "Airtel Money",
            "mpesa": "M-Pesa",
            "cash": "Cash à la livraison",
        }[self.value]


class CancelReason(StrEnum):
    CHANGED_MIND = "changed_mind"
    ORDERED_BY_MISTAKE = "ordered_by_mistake"
    TOO_SLOW = "too_slow"
    CHEAPER_ELSEWHERE = "cheaper_elsewhere"
    OTHER = "other"
    # set by the system, never chosen by the client
    EXPIRED = "expired"
