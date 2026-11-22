import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.documents.domain.errors import ReceiptUnavailable
from apps.documents.domain.tables import RenderedFile
from apps.documents.models import DeliveryReceipt
from apps.documents.services.contracts import PdfRenderer, QrCode
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import OrderDetail

RECEIPT_TEMPLATE = "documents/delivery_receipt.html"
SIGNING_SALT = "celebobo.documents.delivery-receipt"
# a delivered order stays delivered for the receipt even once returned
RECEIPTED = frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED})
CONTACT_HIDDEN = "Coordonnées masquées (7 jours après la livraison)"


def sign(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return salted_hmac(SIGNING_SALT, canonical, algorithm="sha256").hexdigest()


def snapshot(order: OrderDetail) -> dict[str, Any]:
    """Everything the receipt states, as plain values: what gets signed."""
    delivery = next(
        (entry for entry in reversed(order.history) if entry.status is OrderStatus.DELIVERED),
        None,
    )
    return {
        "order_number": order.summary.number,
        # local time: what the client and the reseller saw at handover
        "ordered_at": timezone.localtime(order.summary.created_at).isoformat(),
        "delivered_at": timezone.localtime(delivery.at).isoformat() if delivery else None,
        "confirmation": delivery.note if delivery else "",
        "confirmed_by": (delivery.actor_name or "") if delivery else "",
        "client": order.client.name,
        "reseller": order.reseller.name if order.reseller else "",
        "pickup": order.delivery_method.value == "pickup",
        "address": (
            order.pickup_address
            or f"{order.address.line1}, {order.address.quarter}, {order.address.city}, "
            f"{order.address.country}"
        ),
        "recipient": f"{order.address.recipient} · {order.address.phone}",
        "payment_method": order.payment_method.label,
        "items": [
            {
                "name": item.name,
                "variant": item.variant_label,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "total": str(item.total),
                "serials": list(item.serials),
            }
            for item in order.items
        ],
        "subtotal": str(order.subtotal),
        "discount": str(order.discount),
        "points": str(order.points),
        "shipping_fee": str(order.shipping_fee),
        "total": str(order.summary.total),
    }


def _without_contact(payload: Mapping[str, Any]) -> dict[str, Any]:
    pickup = bool(payload.get("pickup"))
    return {
        **payload,
        "recipient": CONTACT_HIDDEN,
        # free text (a staff reason for a delivery confirmed without the code) may repeat them
        "confirmation": "",
        # a pickup happens at the shop's address, which is not the client's
        "address": payload.get("address", "") if pickup else CONTACT_HIDDEN,
    }


def _moment(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True, slots=True)
class Verification:
    valid: bool
    receipt: DeliveryReceipt | None = None


class ReceiptService:
    def __init__(
        self,
        renderer: PdfRenderer,
        branding: Mapping[str, str],
        *,
        clock: Callable[[], datetime],
        verify_page: str,
        qr: QrCode,
    ) -> None:
        self._verify_page = verify_page
        self._qr = qr
        self._renderer = renderer
        self._branding = branding
        self._clock = clock

    # once per order: a second call returns the receipt already issued
    def issue(self, order: OrderDetail) -> DeliveryReceipt:
        if order.summary.status not in RECEIPTED:
            raise ReceiptUnavailable
        existing = DeliveryReceipt.objects.filter(order_id=order.summary.id).first()
        if existing is not None:
            return existing
        payload = snapshot(order)
        receipt, _ = DeliveryReceipt.objects.get_or_create(
            order_id=order.summary.id,
            defaults={
                "number": f"R-{order.summary.number}",
                "payload": payload,
                "signature": sign(payload),
                "issued_at": self._clock(),
            },
        )
        return receipt

    # contact_hidden: printed for a reseller past the return period, without the client's phone
    # and delivery address; the signed payload itself is unchanged and still verifies
    def render(self, receipt: DeliveryReceipt, *, contact_hidden: bool = False) -> RenderedFile:
        link = f"{self._verify_page}?" + urlencode(
            {"numero": receipt.number, "signature": receipt.signature}
        )
        content = self._renderer.render(
            RECEIPT_TEMPLATE,
            {
                "receipt": _without_contact(receipt.payload) if contact_hidden else receipt.payload,
                "number": receipt.number,
                "signature": receipt.signature,
                "issued_at": receipt.issued_at,
                "ordered_at": _moment(receipt.payload.get("ordered_at")),
                "delivered_at": _moment(receipt.payload.get("delivered_at")),
                # the public page that checks this receipt, filled in: as a link and a QR code
                "verify_link": link,
                "verify_qr": self._qr.data_uri(link),
                "verify_page": self._verify_page,
                **self._branding,
            },
        )
        return RenderedFile(
            content=content,
            filename=f"recu-livraison-{receipt.payload['order_number']}.pdf",
            content_type="application/pdf",
        )

    def mark_emailed(self, receipt: DeliveryReceipt) -> None:
        receipt.emailed_at = self._clock()
        receipt.save(update_fields=["emailed_at"])

    # the content must still match its signature: a receipt edited afterwards no longer verifies
    @staticmethod
    def verify(number: str, signature: str) -> Verification:
        receipt = DeliveryReceipt.objects.filter(number=number.strip().upper()).first()
        if receipt is None:
            return Verification(valid=False)
        valid = constant_time_compare(receipt.signature, signature.strip().lower()) and (
            constant_time_compare(sign(receipt.payload), receipt.signature)
        )
        return Verification(valid=valid, receipt=receipt if valid else None)
