from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cagnotte.api.v1.serializers import (
    CampaignInputSerializer,
    CampaignOutput,
    CurrentCampaignOutput,
    MyRewardOutput,
    PayRewardInput,
    RewardFiltersInput,
    RewardOutput,
)
from apps.cagnotte.domain.commands import CampaignInput, PayReward
from apps.cagnotte.domain.rules import RewardStatus
from apps.cagnotte.facades import CagnotteFacade
from apps.cagnotte.permissions import CAGNOTTE_MANAGE, CAGNOTTE_PAY, CAGNOTTE_VIEW_OWN
from core.api.idempotency import idempotent
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class CurrentCampaignViewSet(UseCaseViewSet):
    """The Cagnotte operation running now, with its conditions (loyalty policy), or none."""

    permission_classes = (AllowAny,)
    cagnotte = Inject(CagnotteFacade)

    @extend_schema(responses=CurrentCampaignOutput)
    def retrieve(self, request: Request) -> Response:
        return Response(CurrentCampaignOutput({"campaign": self.cagnotte.current()}).data)


class MyRewardsViewSet(UseCaseViewSet):
    action_permissions = {"list": (CAGNOTTE_VIEW_OWN,)}
    cagnotte = Inject(CagnotteFacade)

    @extend_schema(responses=MyRewardOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(MyRewardOutput, self.cagnotte.mine(self.actor), many=True)


class CampaignViewSet(UseCaseViewSet):
    """Cagnotte operations: one at a time, conditions fixed once started."""

    action_permissions = {
        "list": (CAGNOTTE_MANAGE,),
        "create": (CAGNOTTE_MANAGE,),
        "retrieve": (CAGNOTTE_MANAGE,),
        "update": (CAGNOTTE_MANAGE,),
        "destroy": (CAGNOTTE_MANAGE,),
        "end": (CAGNOTTE_MANAGE,),
    }
    cagnotte = Inject(CagnotteFacade)

    @extend_schema(responses=CampaignOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(CampaignOutput, self.cagnotte.campaigns(), many=True)

    @extend_schema(request=CampaignInputSerializer, responses={201: CampaignOutput})
    @idempotent()
    def create(self, request: Request) -> Response:
        data = self.parse(CampaignInputSerializer, into=CampaignInput)
        return self.respond(CampaignOutput, self.cagnotte.create(self.actor, data), status=201)

    @extend_schema(responses=CampaignOutput)
    def retrieve(self, request: Request, campaign_id: int) -> Response:
        return self.respond(CampaignOutput, self.cagnotte.campaign(campaign_id))

    @extend_schema(request=CampaignInputSerializer, responses=CampaignOutput)
    def update(self, request: Request, campaign_id: int) -> Response:
        data = self.parse(CampaignInputSerializer, into=CampaignInput)
        return self.respond(CampaignOutput, self.cagnotte.update(self.actor, campaign_id, data))

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, campaign_id: int) -> Response:
        self.cagnotte.delete(self.actor, campaign_id)
        return Response(status=204)

    @extend_schema(request=None, responses=CampaignOutput)
    def end(self, request: Request, campaign_id: int) -> Response:
        return self.respond(CampaignOutput, self.cagnotte.end(self.actor, campaign_id))


class RewardViewSet(UseCaseViewSet):
    """Cashbacks paid by Mobile Money: staff send them once the trial is over."""

    action_permissions = {"list": (CAGNOTTE_PAY,), "pay": (CAGNOTTE_PAY,)}
    cagnotte = Inject(CagnotteFacade)

    @extend_schema(parameters=[RewardFiltersInput], responses=page_of(RewardOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(RewardFiltersInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        status = RewardStatus(filters["status"]) if filters.get("status") else None
        rows, total = self.cagnotte.rewards(
            status=status, due=filters["due"], offset=page.offset, limit=page.page_size
        )
        return page_response(request, page, total=total, results=RewardOutput(rows, many=True).data)

    @extend_schema(request=PayRewardInput, responses=RewardOutput)
    def pay(self, request: Request, reward_id: int) -> Response:
        command = self.parse(PayRewardInput, into=PayReward)
        return self.respond(RewardOutput, self.cagnotte.pay(self.actor, reward_id, command))
