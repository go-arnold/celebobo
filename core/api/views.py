from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

from django.db.models import Model, QuerySet
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from core.api.actor import actor_from_user
from core.api.pagination import MetaPaginationMixin
from core.api.permissions import requires
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.observability import context

if TYPE_CHECKING:
    from rest_framework.permissions import _SupportsHasPermission


class ActorAwareView(APIView):
    actor: Actor
    action_permissions: ClassVar[Mapping[str, Sequence[str]]] = MappingProxyType({})

    def get_permissions(self) -> list["_SupportsHasPermission"]:
        permissions = list(super().get_permissions())
        required = self.action_permissions.get(self._permission_key())
        if required:
            permissions.append(requires(*required)())
        return permissions

    def perform_authentication(self, request: Request) -> None:
        super().perform_authentication(request)
        self.actor = actor_from_user(request.user)
        context.bind(
            user_id=self.actor.user_id,
            role=self.actor.role.value,
            api_version=getattr(request, "version", None),
        )

    def serializer_context(self) -> dict[str, Any]:
        return {"request": self.request, "view": self, "actor": self.actor}

    def user_id(self) -> int:
        if self.actor.user_id is None:
            raise Unauthenticated
        return self.actor.user_id

    def _permission_key(self) -> str:
        action = getattr(self, "action", None)
        return action if isinstance(action, str) else str(self.request.method).lower()


class UseCaseViewSet(ViewSetMixin, ActorAwareView):
    def parse[T](
        self,
        serializer_class: type[BaseSerializer[Any]],
        *,
        into: type[T],
        data: Any = None,
        partial: bool = False,
        **extra: Any,
    ) -> T:
        return into(**{**self.validated(serializer_class, data=data, partial=partial), **extra})

    def validated(
        self,
        serializer_class: type[BaseSerializer[Any]],
        *,
        data: Any = None,
        partial: bool = False,
    ) -> Any:
        serializer = serializer_class(
            data=self.request.data if data is None else data,
            partial=partial,
            context=self.serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def respond(
        self,
        serializer_class: type[BaseSerializer[Any]],
        instance: Any,
        *,
        status: int = 200,
        many: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        serializer = serializer_class(instance, many=many, context=self.serializer_context())
        return Response(serializer.data, status=status, headers=dict(headers or {}))


class SelectorViewSet[M: Model](ViewSetMixin, ActorAwareView, GenericAPIView[M]):
    output_serializer_class: type[BaseSerializer[M]]

    def select(self, actor: Actor) -> QuerySet[M]:
        raise NotImplementedError

    def list_meta(self, queryset: QuerySet[M]) -> Mapping[str, Any]:
        return {}

    def get_queryset(self) -> QuerySet[M]:
        return self.select(self.actor)

    def get_serializer_class(self) -> type[BaseSerializer[M]]:
        return self.output_serializer_class

    def get_serializer_context(self) -> dict[str, Any]:
        return {**super().get_serializer_context(), "actor": self.actor}

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is None:
            return Response(self.get_serializer(queryset, many=True).data)
        if isinstance(self.paginator, MetaPaginationMixin):
            self.paginator.set_meta(**self.list_meta(queryset))
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(self.get_serializer(self.get_object()).data)
