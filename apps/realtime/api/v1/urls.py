from django.urls import path

from apps.realtime.api.v1.views import PresenceViewSet

urlpatterns = [
    path("bo/presence/", PresenceViewSet.as_view({"get": "list"}), name="presence"),
]
