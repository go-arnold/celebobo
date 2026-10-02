from typing import Any
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.documents.api.v1.serializers import (
    AnalyticsReportInput,
    JobOutput,
    ProductsExportInput,
    ProductsImportInput,
    SalesExportInput,
)
from apps.documents.domain.enums import JobFormat, JobKind
from apps.documents.domain.read_models import JobView
from apps.documents.domain.tables import RenderedFile
from apps.documents.facades import DocumentJobFacade, InvoiceFacade
from apps.documents.permissions import (
    EXPORTS_PRODUCTS,
    EXPORTS_SALES,
    IMPORTS_PRODUCTS,
    INVOICES_VIEW,
    INVOICES_VIEW_OWN,
    JOBS_VIEW_OWN,
    REPORTS_ANALYTICS,
)
from core.api.pagination import page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


def file_response(file: RenderedFile, *, inline: bool = False) -> HttpResponse:
    response = HttpResponse(file.content, content_type=file.content_type)
    disposition = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{file.filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


def json_params(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in values.items()
        if value not in (None, "")
    }


class ExportViewSet(UseCaseViewSet):
    action_permissions = {
        "sales": (EXPORTS_SALES,),
        "products": (EXPORTS_PRODUCTS,),
        "analytics": (REPORTS_ANALYTICS,),
        "products_import": (IMPORTS_PRODUCTS,),
    }
    documents = Inject(DocumentJobFacade)

    @extend_schema(request=SalesExportInput, responses={202: JobOutput})
    def sales(self, request: Request) -> Response:
        params = dict(self.validated(SalesExportInput))
        export_format = params.pop("format")
        return self._accepted(
            self.documents.request(
                self.actor, JobKind.SALES_EXPORT, export_format, json_params(params)
            )
        )

    @extend_schema(request=ProductsExportInput, responses={202: JobOutput})
    def products(self, request: Request) -> Response:
        export_format = self.validated(ProductsExportInput)["format"]
        return self._accepted(
            self.documents.request(self.actor, JobKind.PRODUCTS_EXPORT, export_format, {})
        )

    @extend_schema(request=AnalyticsReportInput, responses={202: JobOutput})
    def analytics(self, request: Request) -> Response:
        params = json_params(dict(self.validated(AnalyticsReportInput)))
        return self._accepted(
            self.documents.request(self.actor, JobKind.ANALYTICS_REPORT, JobFormat.PDF, params)
        )

    @extend_schema(request={"multipart/form-data": ProductsImportInput}, responses={202: JobOutput})
    def products_import(self, request: Request) -> Response:
        data = self.validated(ProductsImportInput)
        job = self.documents.request_import(
            self.actor, data["file"].read(), dry_run=data["dry_run"]
        )
        return self._accepted(job)

    def get_parsers(self) -> list[Any]:
        if getattr(self, "action", None) == "products_import":
            return [MultiPartParser(), FormParser()]
        return super().get_parsers()

    def _accepted(self, job: JobView) -> Response:
        return self.respond(JobOutput, job, status=202)


class JobViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (JOBS_VIEW_OWN,),
        "retrieve": (JOBS_VIEW_OWN,),
        "download": (JOBS_VIEW_OWN,),
    }
    documents = Inject(DocumentJobFacade)

    @extend_schema(responses=JobOutput(many=True))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        jobs, total = self.documents.page(self.actor, offset=page.offset, limit=page.page_size)
        return page_response(request, page, total=total, results=JobOutput(jobs, many=True).data)

    @extend_schema(responses=JobOutput)
    def retrieve(self, request: Request, job_id: UUID) -> Response:
        return self.respond(JobOutput, self.documents.detail(self.actor, job_id))

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    def download(self, request: Request, job_id: UUID) -> HttpResponse:
        return file_response(self.documents.download(self.actor, job_id))


class InvoiceViewSet(UseCaseViewSet):
    action_permissions = {"mine": (INVOICES_VIEW_OWN,), "backoffice": (INVOICES_VIEW,)}
    invoices = Inject(InvoiceFacade)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def mine(self, request: Request, number: str) -> HttpResponse:
        return file_response(self.invoices.for_client(self.actor, number), inline=True)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def backoffice(self, request: Request, order_id: int) -> HttpResponse:
        return file_response(self.invoices.for_backoffice(self.actor, order_id), inline=True)
