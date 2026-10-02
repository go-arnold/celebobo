from dataclasses import dataclass
from typing import Any

from django.contrib.auth.models import Group
from django.db.models import QuerySet
from django.urls import include, path
from rest_framework import routers, serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.idempotency import idempotent
from core.api.pagination import PaginationStyle, paginated
from core.api.views import SelectorViewSet, UseCaseViewSet
from core.domain.actor import Actor
from core.domain.errors import InsufficientStock


@dataclass(frozen=True, slots=True)
class ReserveStock:
    product_id: int
    quantity: int
    requested_by: int | None


class ReserveStockInput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=10)


class ReservationOutput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    requested_by = serializers.IntegerField(allow_null=True)


class GroupOutput(serializers.ModelSerializer[Group]):
    class Meta:
        model = Group
        fields = ("id", "name")


calls: list[ReserveStock] = []


class ReservationViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)

    @idempotent()
    def create(self, request: Request) -> Response:
        command = self.parse(ReserveStockInput, into=ReserveStock, requested_by=self.actor.user_id)
        if command.quantity > 5:
            raise InsufficientStock(meta={"available": 5})
        calls.append(command)
        return self.respond(ReservationOutput, command, status=201)


class GroupViewSet(SelectorViewSet[Group]):
    permission_classes = (AllowAny,)
    output_serializer_class = GroupOutput
    pagination_class = paginated(page_size=2)

    def select(self, actor: Actor) -> QuerySet[Group]:
        return Group.objects.order_by("name")

    def list_meta(self, queryset: QuerySet[Group]) -> dict[str, Any]:
        return {"total_groups": queryset.count()}


class GroupFeedViewSet(GroupViewSet):
    pagination_class = paginated(PaginationStyle.CURSOR, page_size=2, ordering="name")


router = routers.SimpleRouter()
router.register("reservations", ReservationViewSet, basename="reservation")
router.register("groups", GroupViewSet, basename="group")
router.register("group-feed", GroupFeedViewSet, basename="group-feed")

urlpatterns = [
    path("api/v1/", include((router.urls, "v1"), namespace="v1")),
    path("", include("config.urls")),
]

handler404 = "core.api.exceptions.not_found"
handler500 = "core.api.exceptions.server_error"
