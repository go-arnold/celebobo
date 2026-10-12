from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.loyalty.api.v1.serializers import LoyaltySettingsInput, ProgrammesOutput
from apps.loyalty.domain.settings import LoyaltySettingsChanges
from apps.loyalty.facades import LoyaltyFacade
from apps.loyalty.permissions import LOYALTY_MANAGE
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
