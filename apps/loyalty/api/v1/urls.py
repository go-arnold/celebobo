from django.urls import path

from apps.loyalty.api.v1.views import (
    LoyaltySettingsViewSet,
    MemberAdminViewSet,
    MembershipRequestAdminViewSet,
    MyMembershipViewSet,
)

urlpatterns = [
    path(
        "bo/loyalty/settings/",
        LoyaltySettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-loyalty-settings",
    ),
    path("me/membership/", MyMembershipViewSet.as_view({"get": "retrieve"}), name="my-membership"),
    path(
        "me/membership/trial/",
        MyMembershipViewSet.as_view({"post": "trial"}),
        name="my-membership-trial",
    ),
    path(
        "me/membership/requests/",
        MyMembershipViewSet.as_view({"post": "subscribe"}),
        name="my-membership-requests",
    ),
    path(
        "me/membership/requests/<id:request_id>/cancel/",
        MyMembershipViewSet.as_view({"post": "cancel"}),
        name="my-membership-request-cancel",
    ),
    path(
        "bo/membership/requests/",
        MembershipRequestAdminViewSet.as_view({"get": "list"}),
        name="bo-membership-requests",
    ),
    path(
        "bo/membership/requests/<id:request_id>/confirm/",
        MembershipRequestAdminViewSet.as_view({"post": "confirm"}),
        name="bo-membership-request-confirm",
    ),
    path(
        "bo/membership/requests/<id:request_id>/reject/",
        MembershipRequestAdminViewSet.as_view({"post": "reject"}),
        name="bo-membership-request-reject",
    ),
    path("bo/memberships/", MemberAdminViewSet.as_view({"get": "list"}), name="bo-memberships"),
]
