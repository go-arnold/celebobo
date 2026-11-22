from django.urls import path

from apps.warranty.api.v1.views import ClaimViewSet, ClientClaimViewSet

urlpatterns = [
    path(
        "me/orders/<id:order_id>/claimable/",
        ClientClaimViewSet.as_view({"get": "claimable"}),
        name="my-order-claimable",
    ),
    path(
        "me/claims/",
        ClientClaimViewSet.as_view({"get": "list", "post": "create"}),
        name="my-claims",
    ),
    path(
        "me/claims/<id:claim_id>/",
        ClientClaimViewSet.as_view({"get": "retrieve"}),
        name="my-claim",
    ),
    path("bo/claims/", ClaimViewSet.as_view({"get": "list"}), name="bo-claims"),
    path("bo/claims/<id:claim_id>/", ClaimViewSet.as_view({"get": "retrieve"}), name="bo-claim"),
    path(
        "bo/claims/<id:claim_id>/answer/",
        ClaimViewSet.as_view({"post": "answer"}),
        name="bo-claim-answer",
    ),
    path(
        "bo/claims/<id:claim_id>/receive/",
        ClaimViewSet.as_view({"post": "receive"}),
        name="bo-claim-receive",
    ),
    path(
        "bo/claims/<id:claim_id>/diagnose/",
        ClaimViewSet.as_view({"post": "diagnose"}),
        name="bo-claim-diagnose",
    ),
    path(
        "bo/claims/<id:claim_id>/repaired/",
        ClaimViewSet.as_view({"post": "finish_repair"}),
        name="bo-claim-repaired",
    ),
]
