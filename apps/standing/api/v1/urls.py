from django.urls import path

from apps.standing.api.v1.views import SanctionViewSet, StandingViewSet

urlpatterns = [
    path("bo/standing/", StandingViewSet.as_view({"get": "retrieve"}), name="bo-standing"),
    path(
        "bo/standing/review/",
        StandingViewSet.as_view({"post": "review"}),
        name="bo-standing-review",
    ),
    path(
        "bo/sanctions/",
        SanctionViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-sanctions",
    ),
    path(
        "bo/sanctions/<id:sanction_id>/explain/",
        SanctionViewSet.as_view({"post": "explain"}),
        name="bo-sanction-explain",
    ),
    path(
        "bo/sanctions/<id:sanction_id>/decide/",
        SanctionViewSet.as_view({"post": "decide"}),
        name="bo-sanction-decide",
    ),
]
