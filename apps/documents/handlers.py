from apps.documents.domain.events import JobRequested
from apps.documents.facades import DocumentJobFacade, ReceiptFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from core.container import container
from core.events.bus import event_bus


@event_bus.on(JobRequested, background=True)
def run_requested_job(event: JobRequested) -> None:
    documents = container.resolve(DocumentJobFacade)
    try:
        documents.run(event.job_id)
    except Exception:
        documents.fail(event.job_id)
        raise


@event_bus.on(OrderStatusChanged, background=True)
def issue_delivery_receipt(event: OrderStatusChanged) -> None:
    if event.status is OrderStatus.DELIVERED:
        container.resolve(ReceiptFacade).delivered(event.order_id)
