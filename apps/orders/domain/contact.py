"""How long the delivering reseller sees the client's contact details (privacy policy §4 and §6).

The reseller gets the client's phone and delivery address to deliver the order. Once the order
is delivered and the 7-day return period is over, they are hidden from the reseller's space;
the order keeps them for staff and accounting. The rule is applied when reading, never by
deleting data.
"""

from datetime import datetime, timedelta

from apps.orders.domain.enums import OrderStatus

# the return period after delivery, fixed by the privacy policy ("7 jours après la livraison")
RESELLER_CONTACT_DAYS = 7
RESELLER_CONTACT_WINDOW = timedelta(days=RESELLER_CONTACT_DAYS)

# delivered once: the window runs from the (last) delivery
HANDED_OVER = frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED})


def contact_cutoff(now: datetime) -> datetime:
    """Orders delivered at or before this moment no longer show the client's contact details."""
    return now - RESELLER_CONTACT_WINDOW


def reseller_contact_hidden(
    status: OrderStatus, delivered_at: datetime | None, *, now: datetime
) -> bool:
    """Whether the assigned reseller has lost the client's phone and address on this order.

    - open orders (not delivered yet, whatever their age): visible, the reseller must deliver;
    - delivered or returned: visible for 7 days after delivery, then hidden;
    - cancelled: hidden at once, there is nothing left to deliver.

    A delivered order without its delivery date is treated as past the window (fail closed).
    """
    if status is OrderStatus.CANCELLED:
        return True
    if status in HANDED_OVER:
        return delivered_at is None or delivered_at <= contact_cutoff(now)
    return False
