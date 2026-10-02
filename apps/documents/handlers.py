from apps.documents.domain.events import JobRequested
from apps.documents.facades import DocumentJobFacade
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
