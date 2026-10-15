from django.urls import path

from apps.loyalty.api.v1.views import (
    LoyaltyRuleViewSet,
    LoyaltySettingsViewSet,
    MyCashbackViewSet,
    MyPointsViewSet,
    MyPointTransactionsViewSet,
)

urlpatterns = [
    path(
        "bo/loyalty/settings/",
        LoyaltySettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-loyalty-settings",
    ),
    path(
        "bo/loyalty/rules/",
        LoyaltyRuleViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-loyalty-rules",
    ),
    path(
        "bo/loyalty/rules/<int:rule_id>/",
        LoyaltyRuleViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="bo-loyalty-rule-detail",
    ),
    path("me/cashback/", MyCashbackViewSet.as_view({"get": "retrieve"}), name="my-cashback"),
    path("me/points/", MyPointsViewSet.as_view({"get": "retrieve"}), name="my-points"),
    path(
        "me/points/transactions/",
        MyPointTransactionsViewSet.as_view({"get": "list"}),
        name="my-point-transactions",
    ),
]
