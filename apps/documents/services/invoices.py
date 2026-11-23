from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

from apps.documents.domain.errors import InvoiceUnavailable
from apps.documents.domain.tables import RenderedFile
from apps.documents.services.contracts import PdfRenderer, PointsStatements
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import OrderDetail
from apps.orders.domain.serials import TRIAL_DAYS, WARRANTY_MONTHS, warranty_end

INVOICE_TEMPLATE = "documents/invoice.html"


@dataclass(frozen=True, slots=True)
class WarrantyDates:
    """Printed on the invoice: the dates once delivered, the durations before (warranty policy)."""

    trial_days: int
    warranty_months: int
    trial_until: date | None
    warranty_until: date | None


def warranty_dates(order: OrderDetail) -> WarrantyDates:
    delivered = [entry.at for entry in order.history if entry.status is OrderStatus.DELIVERED]
    if not delivered:
        return WarrantyDates(TRIAL_DAYS, WARRANTY_MONTHS, None, None)
    day = timezone.localtime(delivered[-1]).date()
    return WarrantyDates(
        TRIAL_DAYS, WARRANTY_MONTHS, day + timedelta(days=TRIAL_DAYS), warranty_end(day)
    )


class InvoiceBuilder:
    def __init__(
        self, renderer: PdfRenderer, branding: Mapping[str, str], points: PointsStatements
    ) -> None:
        self._renderer = renderer
        self._branding = branding
        self._points = points

    def build(self, order: OrderDetail, *, points: bool = True) -> RenderedFile:
        if order.summary.status is OrderStatus.CANCELLED:
            raise InvoiceUnavailable
        content = self._renderer.render(
            INVOICE_TEMPLATE,
            {
                "order": order,
                "issued_at": timezone.localtime(),
                "warranty": warranty_dates(order),
                # the order's discount holds the Cagnotte discount and the coupon: one line each
                "coupon_discount": order.discount - order.campaign_discount,
                # the client's points statement, printed on each invoice (loyalty policy); not
                # on a reseller's copy (it gives the client's purchase totals), nor for a deleted
                # or anonymised account, whose points history is gone (it would be recomputed at
                # today's rate and shown as pending)
                "points": self._points.statement(order.client.id, order.summary.id)
                if points and not order.client.anonymized
                else None,
                **self._branding,
            },
        )
        return RenderedFile(
            content=content,
            filename=f"facture-{order.summary.number}.pdf",
            content_type="application/pdf",
        )
