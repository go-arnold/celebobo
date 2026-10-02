from uuid import UUID

from django.http import HttpResponseBase
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle

from apps.assistant.api.v1.serializers import (
    AssistantSessionDetailOutput,
    AssistantSessionOutput,
    AssistantStatsOutput,
    LogFiltersInput,
    MessageInput,
    QuestionLogOutput,
)
from apps.assistant.api.v1.streaming import collect, event_stream
from apps.assistant.domain.queries import LogFilters
from apps.assistant.facades import AssistantFacade, AssistantInsightsFacade
from apps.assistant.permissions import (
    ASSISTANT_CHAT,
    ASSISTANT_HISTORY,
    ASSISTANT_LOGS,
    EMBEDDINGS_REINDEX,
)
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject

STREAM_PARAMETER = OpenApiParameter(
    "stream", bool, required=False, description="false renvoie la réponse complète en JSON."
)


class AssistantSessionViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    action_permissions = {
        "create": (ASSISTANT_CHAT,),
        "list": (ASSISTANT_HISTORY,),
        "retrieve": (ASSISTANT_CHAT,),
        "destroy": (ASSISTANT_CHAT,),
        "message": (ASSISTANT_CHAT,),
    }
    assistant = Inject(AssistantFacade)

    def get_throttles(self) -> list[BaseThrottle]:
        self.throttle_scope = "assistant" if getattr(self, "action", None) == "message" else ""
        return list(super().get_throttles())

    @extend_schema(request=None, responses={201: AssistantSessionOutput})
    def create(self, request: Request) -> Response:
        return self.respond(AssistantSessionOutput, self.assistant.open(self.actor), status=201)

    @extend_schema(responses=page_of(AssistantSessionOutput))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=50)
        sessions, total = self.assistant.sessions(
            self.actor, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request, page, total=total, results=AssistantSessionOutput(sessions, many=True).data
        )

    @extend_schema(responses=AssistantSessionDetailOutput)
    def retrieve(self, request: Request, session_id: UUID) -> Response:
        return self.respond(
            AssistantSessionDetailOutput, self.assistant.detail(self.actor, session_id)
        )

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, session_id: UUID) -> Response:
        self.assistant.close(self.actor, session_id)
        return Response(status=204)

    @extend_schema(
        request=MessageInput,
        parameters=[STREAM_PARAMETER],
        responses={
            (200, "text/event-stream"): OpenApiTypes.STR,
            (200, "application/json"): OpenApiTypes.OBJECT,
        },
    )
    def message(self, request: Request, session_id: UUID) -> HttpResponseBase:
        content = self.validated(MessageInput)["content"]
        pending = self.assistant.ask(self.actor, session_id, content)
        events = self.assistant.reply(self.actor, pending)
        if request.query_params.get("stream") == "false":
            return Response(collect(events))
        return event_stream(events)


class AssistantBackofficeViewSet(UseCaseViewSet):
    action_permissions = {"logs": (ASSISTANT_LOGS,), "reindex": (EMBEDDINGS_REINDEX,)}
    insights = Inject(AssistantInsightsFacade)

    @extend_schema(parameters=[LogFiltersInput], responses=page_of(QuestionLogOutput))
    def logs(self, request: Request) -> Response:
        filters = self.parse(LogFiltersInput, into=LogFilters, data=request.query_params)
        page = page_request(request, default_size=50, max_size=200)
        logs, total = self.insights.logs(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=total,
            results=QuestionLogOutput(logs, many=True).data,
            meta={"stats": AssistantStatsOutput(self.insights.stats(filters)).data},
        )

    @extend_schema(request=None, responses={202: None})
    def reindex(self, request: Request) -> Response:
        self.insights.request_reindex(self.actor)
        return Response(status=202)
