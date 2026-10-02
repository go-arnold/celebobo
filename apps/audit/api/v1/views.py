from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit.api.v1.serializers import (
    ChangeFiltersInput,
    ChangeOutput,
    EventFiltersInput,
    EventOutput,
    TrackedTypeOutput,
)
from apps.audit.domain.queries import ChangeFilters, EventFilters
from apps.audit.facades import AuditFacade
from apps.audit.permissions import AUDIT_VIEW
from core.api.pagination import page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class AuditViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("changes", "change", "events", "object_types"), (AUDIT_VIEW,)
    )
    audit = Inject(AuditFacade)

    @extend_schema(parameters=[ChangeFiltersInput], responses=ChangeOutput(many=True))
    def changes(self, request: Request) -> Response:
        filters = self.parse(ChangeFiltersInput, into=ChangeFilters, data=request.query_params)
        page = page_request(request, default_size=50, max_size=200)
        entries, total = self.audit.changes(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request, page, total=total, results=ChangeOutput(entries, many=True).data
        )

    @extend_schema(responses=ChangeOutput)
    def change(self, request: Request, entry_id: int) -> Response:
        return self.respond(ChangeOutput, self.audit.change(entry_id))

    @extend_schema(parameters=[EventFiltersInput], responses=EventOutput(many=True))
    def events(self, request: Request) -> Response:
        filters = self.parse(EventFiltersInput, into=EventFilters, data=request.query_params)
        page = page_request(request, default_size=50, max_size=200)
        entries, total = self.audit.events(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=total,
            results=EventOutput(entries, many=True).data,
            meta={"event_types": self.audit.event_types()},
        )

    @extend_schema(responses=TrackedTypeOutput(many=True))
    def object_types(self, request: Request) -> Response:
        return self.respond(TrackedTypeOutput, self.audit.tracked_types(), many=True)
