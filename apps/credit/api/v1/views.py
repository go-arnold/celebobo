from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.credit.api.v1.serializers import StoreCreditOutput
from apps.credit.facades import StoreCreditFacade
from apps.credit.permissions import STORE_CREDIT_VIEW_OWN
from core.api.views import UseCaseViewSet
from core.container import Inject


class StoreCreditViewSet(UseCaseViewSet):
    """« Mon avoir »: the balance, the next expiry and the movements."""

    action_permissions = {"retrieve": (STORE_CREDIT_VIEW_OWN,)}
    credit = Inject(StoreCreditFacade)

    @extend_schema(responses=StoreCreditOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(StoreCreditOutput, self.credit.balance(self.actor))
