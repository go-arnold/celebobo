from django.urls import path

from apps.loyalty.api.v1.views import LoyaltySettingsViewSet, MyPointsViewSet

urlpatterns = [
    path(
        "bo/loyalty/settings/",
        LoyaltySettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-loyalty-settings",
    ),
    path("me/points/", MyPointsViewSet.as_view({"get": "retrieve"}), name="my-points"),
]
