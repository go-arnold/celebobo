from typing import Any
from uuid import UUID

from django.db import transaction

from apps.documents.domain.enums import JobFormat, JobKind, JobStatus
from apps.documents.domain.errors import JobNotReady
from apps.documents.domain.events import JobFinished, JobRequested
from apps.documents.domain.read_models import JobView
from apps.documents.domain.tables import RenderedFile
from apps.documents.models import Job
from apps.documents.selectors import JobSelector, to_job_view
from apps.documents.services.contracts import OrderSource
from apps.documents.services.importer import parse_csv
from apps.documents.services.invoices import InvoiceBuilder
from apps.documents.services.jobs import JobService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade

INTERNAL_ERROR = "Une erreur interne est survenue pendant la génération."


@logged_facade
class DocumentJobFacade:
    def __init__(
        self,
        *,
        jobs: JobService,
        selector: JobSelector,
        publisher: EventPublisher,
        max_import_rows: int,
        max_import_bytes: int,
        retention_days: int,
    ) -> None:
        self._jobs = jobs
        self._selector = selector
        self._publisher = publisher
        self._max_import_rows = max_import_rows
        self._max_import_bytes = max_import_bytes
        self._retention_days = retention_days

    def request(
        self, actor: Actor, kind: JobKind, format: JobFormat, params: dict[str, Any]
    ) -> JobView:
        return self._enqueue(actor, kind, format, params)

    def request_import(self, actor: Actor, upload: bytes, *, dry_run: bool) -> JobView:
        parse_csv(upload, max_rows=self._max_import_rows, max_bytes=self._max_import_bytes)
        return self._enqueue(
            actor, JobKind.PRODUCTS_IMPORT, JobFormat.CSV, {"dry_run": dry_run}, upload=upload
        )

    def run(self, job_id: UUID) -> None:
        with transaction.atomic():
            self._finished(self._jobs.run(job_id))

    def fail(self, job_id: UUID) -> None:
        with transaction.atomic():
            self._finished(self._jobs.fail(job_id, INTERNAL_ERROR))

    def page(self, actor: Actor, *, offset: int, limit: int) -> tuple[list[JobView], int]:
        return self._selector.page(_user_id(actor), offset=offset, limit=limit)

    def detail(self, actor: Actor, job_id: UUID) -> JobView:
        return to_job_view(self._jobs.owned(actor, job_id))

    def download(self, actor: Actor, job_id: UUID) -> RenderedFile:
        job = self._jobs.owned(actor, job_id)
        if job.job_status is not JobStatus.DONE or not job.file:
            raise JobNotReady
        return RenderedFile(
            content=self._jobs.read(job), filename=job.filename, content_type=job.content_type
        )

    def purge(self) -> int:
        with transaction.atomic():
            return self._jobs.purge(retention_days=self._retention_days)

    def _enqueue(
        self,
        actor: Actor,
        kind: JobKind,
        format: JobFormat,
        params: dict[str, Any],
        *,
        upload: bytes | None = None,
    ) -> JobView:
        _user_id(actor)
        with transaction.atomic():
            job = self._jobs.request(actor, kind, format, params, upload=upload)
            self._publisher.publish(JobRequested(job_id=job.pk, actor_id=actor.user_id))
        return to_job_view(job)

    def _finished(self, job: Job | None) -> None:
        if job is None:
            return
        self._publisher.publish(
            JobFinished(
                job_id=job.pk,
                owner_id=job.owner_id,
                kind=job.job_kind,
                status=job.job_status,
            )
        )


@logged_facade
class InvoiceFacade:
    def __init__(self, *, orders: OrderSource, builder: InvoiceBuilder) -> None:
        self._orders = orders
        self._builder = builder

    def for_client(self, actor: Actor, number: str) -> RenderedFile:
        return self._builder.build(self._orders.for_client(_user_id(actor), number))

    def for_backoffice(self, actor: Actor, order_id: int) -> RenderedFile:
        return self._builder.build(self._orders.for_backoffice(actor, order_id))


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id
