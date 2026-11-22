from collections.abc import Mapping

from django.utils import timezone

from apps.documents.domain.errors import InvoiceUnavailable
from apps.documents.domain.tables import RenderedFile
from apps.documents.services.contracts import PdfRenderer, PointsStatements
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import OrderDetail

INVOICE_TEMPLATE = "documents/invoice.html"


class InvoiceBuilder:
    def __init__(
        self, renderer: PdfRenderer, branding: Mapping[str, str], points: PointsStatements
    ) -> None:
        self._renderer = renderer
        self._branding = branding
        self._points = points

    def build(self, order: OrderDetail) -> RenderedFile:
        if order.summary.status is OrderStatus.CANCELLED:
            raise InvoiceUnavailable
        content = self._renderer.render(
            INVOICE_TEMPLATE,
            {
                "order": order,
                "issued_at": timezone.localtime(),
                # the client's points statement, printed on each invoice (loyalty policy); not
                # for a deleted or anonymised account, whose points history is gone (it would be
                # recomputed at today's rate and shown as pending)
                "points": None
                if order.client.anonymized
                else self._points.statement(order.client.id, order.summary.id),
                **self._branding,
            },
        )
        return RenderedFile(
            content=content,
            filename=f"facture-{order.summary.number}.pdf",
            content_type="application/pdf",
        )
