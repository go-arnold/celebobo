from django.urls import path

from apps.cagnotte.api.v1.views import (
    CampaignViewSet,
    CurrentCampaignViewSet,
    MyRewardsViewSet,
    RewardViewSet,
)

urlpatterns = [
    path(
        "cagnotte/current/",
        CurrentCampaignViewSet.as_view({"get": "retrieve"}),
        name="cagnotte-current",
    ),
    path("me/cagnotte/", MyRewardsViewSet.as_view({"get": "list"}), name="me-cagnotte"),
    path(
        "bo/campaigns/",
        CampaignViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-campaigns",
    ),
    path(
        "bo/campaigns/<id:campaign_id>/",
        CampaignViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"}),
        name="bo-campaign",
    ),
    path(
        "bo/campaigns/<id:campaign_id>/end/",
        CampaignViewSet.as_view({"post": "end"}),
        name="bo-campaign-end",
    ),
    path(
        "bo/cagnotte/rewards/",
        RewardViewSet.as_view({"get": "list"}),
        name="bo-cagnotte-rewards",
    ),
    path(
        "bo/cagnotte/rewards/<id:reward_id>/pay/",
        RewardViewSet.as_view({"post": "pay"}),
        name="bo-cagnotte-reward-pay",
    ),
]
