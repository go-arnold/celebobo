from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.v1.backoffice_serializers import (
    CreateUserInput,
    EditUserInput,
    UserFiltersInput,
    UserRowOutput,
)
from apps.accounts.domain.commands import CreateUser, EditUser, UserFilters
from apps.accounts.facades import UserAdminFacade
from apps.accounts.permissions import USERS_MANAGE, USERS_VIEW
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class UserAdminViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (USERS_VIEW,),
        "retrieve": (USERS_VIEW,),
        "create": (USERS_MANAGE,),
        "partial_update": (USERS_MANAGE,),
        "activate": (USERS_MANAGE,),
        "deactivate": (USERS_MANAGE,),
        "send_password_reset": (USERS_MANAGE,),
    }
    users = Inject(UserAdminFacade)

    @extend_schema(parameters=[UserFiltersInput], responses=page_of(UserRowOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(UserFiltersInput, into=UserFilters, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        users, total, counts = self.users.page(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request,
            page,
            total=total,
            results=UserRowOutput(users, many=True).data,
            meta={"counts": counts},
        )

    @extend_schema(request=CreateUserInput, responses={201: UserRowOutput})
    def create(self, request: Request) -> Response:
        command = self.parse(CreateUserInput, into=CreateUser)
        return self.respond(UserRowOutput, self.users.create(self.actor, command), status=201)

    @extend_schema(responses=UserRowOutput)
    def retrieve(self, request: Request, user_id: int) -> Response:
        return self.respond(UserRowOutput, self.users.detail(user_id))

    @extend_schema(request=EditUserInput, responses=UserRowOutput)
    def partial_update(self, request: Request, user_id: int) -> Response:
        command = self.parse(EditUserInput, into=EditUser, partial=True)
        return self.respond(UserRowOutput, self.users.edit(self.actor, user_id, command))

    @extend_schema(request=None, responses=UserRowOutput)
    def activate(self, request: Request, user_id: int) -> Response:
        return self.respond(UserRowOutput, self.users.set_active(self.actor, user_id, active=True))

    @extend_schema(request=None, responses=UserRowOutput)
    def deactivate(self, request: Request, user_id: int) -> Response:
        return self.respond(UserRowOutput, self.users.set_active(self.actor, user_id, active=False))

    @extend_schema(request=None, responses={202: None})
    def send_password_reset(self, request: Request, user_id: int) -> Response:
        self.users.send_password_reset(self.actor, user_id)
        return Response(status=202)
