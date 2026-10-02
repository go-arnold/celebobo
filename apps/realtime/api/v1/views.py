from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_serializer
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response

from apps.realtime.permissions import PRESENCE_VIEW
from apps.realtime.services.presence import PresenceService
from core.api.fields import MAX_INTEGER
from core.api.views import UseCaseViewSet
from core.container import Inject

MAX_IDS = 200


class PresenceQueryInput(serializers.Serializer[Any]):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=MAX_INTEGER),
        allow_empty=False,
        max_length=MAX_IDS,
    )


@extend_schema_serializer(many=False)
class PresenceOutput(serializers.Serializer[Any]):
    online = serializers.ListField(child=serializers.IntegerField())


class PresenceViewSet(UseCaseViewSet):
    action_permissions = {"list": (PRESENCE_VIEW,)}
    presence = Inject(PresenceService)

    @extend_schema(parameters=[PresenceQueryInput], responses=PresenceOutput)
    def list(self, request: Request) -> Response:
        ids = self.validated(PresenceQueryInput, data=request.query_params)["ids"]
        return Response({"online": sorted(self.presence.online(ids))})
