from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.loyalty.api.v1.serializers import (
    BalanceOutput,
    LoyaltyRuleInput,
    LoyaltyRuleOutput,
    LoyaltySettingsInput,
    PointBalanceOutput,
    PointTransactionOutput,
    ProgrammesOutput,
)
from apps.loyalty.domain.settings import LoyaltySettingsChanges
from apps.loyalty.facades import CashbackFacade, LoyaltyFacade, LoyaltyRuleFacade, PointsFacade
from apps.loyalty.permissions import LOYALTY_MANAGE, POINTS_VIEW
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class LoyaltySettingsViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("retrieve", "partial_update"), (LOYALTY_MANAGE,))
    loyalty = Inject(LoyaltyFacade)

    @extend_schema(responses=ProgrammesOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(ProgrammesOutput, self.loyalty.programmes())

    @extend_schema(request=LoyaltySettingsInput, responses=ProgrammesOutput)
    def partial_update(self, request: Request) -> Response:
        changes = self.parse(LoyaltySettingsInput, into=LoyaltySettingsChanges, partial=True)
        return self.respond(ProgrammesOutput, self.loyalty.update(self.actor, changes))


class LoyaltyRuleViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "create", "partial_update", "destroy"), (LOYALTY_MANAGE,)
    )
    rules = Inject(LoyaltyRuleFacade)

    @extend_schema(responses=page_of(LoyaltyRuleOutput))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        rules = self.rules.all()
        start = page.offset
        end = start + page.page_size
        return page_response(
            request,
            page,
            total=len(rules),
            results=LoyaltyRuleOutput(rules[start:end], many=True).data,
        )

    @extend_schema(request=LoyaltyRuleInput, responses=LoyaltyRuleOutput)
    def create(self, request: Request) -> Response:
        data = self.validated(LoyaltyRuleInput)
        rule = self.rules.create(
            actor=self.actor,
            name=data["name"],
            trigger=data["trigger"],
            condition=data.get("condition", {}),
            points_value=data["points_value"],
            is_active=data.get("is_active", True),
            max_per_user=data.get("max_per_user"),
            max_per_day=data.get("max_per_day"),
            cooldown_days=data.get("cooldown_days"),
        )
        return self.respond(LoyaltyRuleOutput, rule, status=201)

    @extend_schema(request=LoyaltyRuleInput, responses=LoyaltyRuleOutput)
    def partial_update(self, request: Request, rule_id: int) -> Response:
        data = self.validated(LoyaltyRuleInput, partial=True)
        changes = {k: v for k, v in data.items() if k != "trigger"}
        rule = self.rules.update(actor=self.actor, rule_id=rule_id, **changes)
        return self.respond(LoyaltyRuleOutput, rule)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, rule_id: int) -> Response:
        self.rules.delete(actor=self.actor, rule_id=rule_id)
        return Response(status=204)


class MyPointsViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("retrieve",), (POINTS_VIEW,))
    points = Inject(PointsFacade)

    @extend_schema(responses=PointBalanceOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(PointBalanceOutput, self.points.mine(self.actor))


class MyPointTransactionsViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list",), (POINTS_VIEW,))
    points = Inject(PointsFacade)

    @extend_schema(responses=page_of(PointTransactionOutput))
    def list(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        rows, total = self.points.transactions(self.actor, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=total,
            results=PointTransactionOutput(rows, many=True).data,
        )


class MyCashbackViewSet(UseCaseViewSet):
    action_permissions = {"retrieve": (POINTS_VIEW,)}
    cashback = Inject(CashbackFacade)

    @extend_schema(responses=BalanceOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(BalanceOutput, self.cashback.mine(self.actor))
