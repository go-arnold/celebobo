from django.urls import path

from apps.assistant.api.v1.views import AssistantBackofficeViewSet, AssistantSessionViewSet

urlpatterns = [
    path(
        "assistant/sessions/",
        AssistantSessionViewSet.as_view({"get": "list", "post": "create"}),
        name="assistant-sessions",
    ),
    path(
        "assistant/sessions/<uuid:session_id>/",
        AssistantSessionViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="assistant-session",
    ),
    path(
        "assistant/sessions/<uuid:session_id>/messages/",
        AssistantSessionViewSet.as_view({"post": "message"}),
        name="assistant-messages",
    ),
    path(
        "bo/assistant/logs/",
        AssistantBackofficeViewSet.as_view({"get": "logs"}),
        name="bo-assistant-logs",
    ),
    path(
        "bo/embeddings/reindex/",
        AssistantBackofficeViewSet.as_view({"post": "reindex"}),
        name="bo-embeddings-reindex",
    ),
]
