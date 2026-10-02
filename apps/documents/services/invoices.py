from collections.abc import Mapping

from django.utils import timezone

from apps.documents.domain.errors import InvoiceUnavailable
from apps.documents.domain.tables import RenderedFile
from apps.documents.services.contracts import PdfRenderer
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import OrderDetail

INVOICE_TEMPLATE = "documents/invoice.html"


class InvoiceBuilder:
    def __init__(self, renderer: PdfRenderer, branding: Mapping[str, str]) -> None:
        self._renderer = renderer
        self._branding = branding

    def build(self, order: OrderDetail) -> RenderedFile:
        if order.summary.status is OrderStatus.CANCELLED:
            raise InvoiceUnavailable
        content = self._renderer.render(
            INVOICE_TEMPLATE,
            {"order": order, "issued_at": timezone.localtime(), **self._branding},
        )
        return RenderedFile(
            content=content,
            filename=f"facture-{order.summary.number}.pdf",
            content_type="application/pdf",
        )
