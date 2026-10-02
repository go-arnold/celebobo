from django.urls import path

from apps.resellers.api.v1.views import (
    ApplicationReviewViewSet,
    ApplicationSubmissionViewSet,
    ReferralViewSet,
    ResellerViewSet,
)

urlpatterns = [
    path(
        "reseller-applications/",
        ApplicationSubmissionViewSet.as_view({"post": "create"}),
        name="reseller-applications",
    ),
    path(
        "bo/reseller-applications/",
        ApplicationReviewViewSet.as_view({"get": "list"}),
        name="bo-reseller-applications",
    ),
    path(
        "bo/reseller-applications/<int:application_id>/",
        ApplicationReviewViewSet.as_view({"get": "retrieve"}),
        name="bo-reseller-application",
    ),
    path(
        "bo/reseller-applications/<int:application_id>/approve/",
        ApplicationReviewViewSet.as_view({"post": "approve"}),
        name="bo-reseller-application-approve",
    ),
    path(
        "bo/reseller-applications/<int:application_id>/reject/",
        ApplicationReviewViewSet.as_view({"post": "reject"}),
        name="bo-reseller-application-reject",
    ),
    path("bo/resellers/", ResellerViewSet.as_view({"get": "list"}), name="bo-resellers"),
    path(
        "bo/resellers/stats/", ResellerViewSet.as_view({"get": "stats"}), name="bo-resellers-stats"
    ),
    path(
        "bo/resellers/<int:reseller_id>/",
        ResellerViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-reseller",
    ),
    path(
        "bo/resellers/<int:reseller_id>/activate/",
        ResellerViewSet.as_view({"post": "activate"}),
        name="bo-reseller-activate",
    ),
    path(
        "bo/resellers/<int:reseller_id>/deactivate/",
        ResellerViewSet.as_view({"post": "deactivate"}),
        name="bo-reseller-deactivate",
    ),
    path(
        "bo/resellers/<int:reseller_id>/invitees/",
        ResellerViewSet.as_view({"get": "invitees"}),
        name="bo-reseller-invitees",
    ),
    path("bo/me/referral/", ReferralViewSet.as_view({"get": "retrieve"}), name="my-referral"),
    path("bo/me/invitees/", ReferralViewSet.as_view({"get": "invitees"}), name="my-invitees"),
]
