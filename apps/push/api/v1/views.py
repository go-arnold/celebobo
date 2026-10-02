from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.push.api.v1.serializers import DeviceOutput, PublicKeyOutput, RegisterDeviceInput
from apps.push.facades import PushFacade
from apps.push.permissions import PUSH_DEVICES
from core.api.views import UseCaseViewSet
from core.container import Inject


class PublicKeyViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    push = Inject(PushFacade)

    @extend_schema(responses=PublicKeyOutput)
    def retrieve(self, request: Request) -> Response:
        public_key, enabled = self.push.public_key()
        return Response({"public_key": public_key, "enabled": enabled})


class DeviceViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list", "create", "destroy"), (PUSH_DEVICES,))
    push = Inject(PushFacade)

    @extend_schema(responses=DeviceOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(DeviceOutput, self.push.devices(self.actor), many=True)

    @extend_schema(request=RegisterDeviceInput, responses={201: DeviceOutput})
    def create(self, request: Request) -> Response:
        device = self.push.register(self.actor, self.validated(RegisterDeviceInput))
        return self.respond(DeviceOutput, device, status=201)

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, device_id: int) -> Response:
        self.push.remove(self.actor, device_id)
        return Response(status=204)
