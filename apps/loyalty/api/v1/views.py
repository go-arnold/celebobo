from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.loyalty.api.v1.serializers import (
    AdminMemberOutput,
    AdminRequestOutput,
    LoyaltySettingsInput,
    MemberFiltersInput,
    MemberOutput,
    MembershipRequestInput,
    ProgrammesOutput,
    RejectInput,
    RequestFiltersInput,
)
from apps.loyalty.domain.membership import MembershipStatus, RequestMembership, RequestStatus
from apps.loyalty.domain.settings import LoyaltySettingsChanges
from apps.loyalty.facades import LoyaltyFacade, MembershipFacade
from apps.loyalty.permissions import LOYALTY_MANAGE, MEMBERSHIP_MANAGE, MEMBERSHIP_SUBSCRIBE
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


class MyMembershipViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("retrieve", "trial", "subscribe", "cancel"), (MEMBERSHIP_SUBSCRIBE,)
    )
    memberships = Inject(MembershipFacade)

    @extend_schema(responses=MemberOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(MemberOutput, self.memberships.mine(self.actor))

    @extend_schema(request=None, responses=MemberOutput)
    def trial(self, request: Request) -> Response:
        return self.respond(MemberOutput, self.memberships.start_trial(self.actor))

    @extend_schema(request=MembershipRequestInput, responses={201: MemberOutput})
    def subscribe(self, request: Request) -> Response:
        command = self.parse(MembershipRequestInput, into=RequestMembership)
        return self.respond(MemberOutput, self.memberships.request(self.actor, command), status=201)

    @extend_schema(request=None, responses=MemberOutput)
    def cancel(self, request: Request, request_id: int) -> Response:
        return self.respond(MemberOutput, self.memberships.cancel(self.actor, request_id))


class MembershipRequestAdminViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(("list", "confirm", "reject"), (MEMBERSHIP_MANAGE,))
    memberships = Inject(MembershipFacade)

    @extend_schema(parameters=[RequestFiltersInput], responses=page_of(AdminRequestOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(RequestFiltersInput, data=request.query_params)
        status = RequestStatus(filters["status"]) if "status" in filters else None
        page = page_request(request, default_size=20, max_size=100)
        rows, total = self.memberships.requests(status, offset=page.offset, limit=page.page_size)
        return page_response(
            request, page, total=total, results=AdminRequestOutput(rows, many=True).data
        )

    @extend_schema(request=None, responses={204: None})
    def confirm(self, request: Request, request_id: int) -> Response:
        self.memberships.confirm(self.actor, request_id)
        return Response(status=204)

    @extend_schema(request=RejectInput, responses={204: None})
    def reject(self, request: Request, request_id: int) -> Response:
        note = self.validated(RejectInput)["note"]
        self.memberships.reject(self.actor, request_id, note)
        return Response(status=204)


class MemberAdminViewSet(UseCaseViewSet):
    action_permissions = {"list": (MEMBERSHIP_MANAGE,)}
    memberships = Inject(MembershipFacade)

    @extend_schema(parameters=[MemberFiltersInput], responses=page_of(AdminMemberOutput))
    def list(self, request: Request) -> Response:
        filters = self.validated(MemberFiltersInput, data=request.query_params)
        status = MembershipStatus(filters["status"]) if "status" in filters else None
        page = page_request(request, default_size=20, max_size=100)
        rows, total = self.memberships.members(status, offset=page.offset, limit=page.page_size)
        return page_response(
            request, page, total=total, results=AdminMemberOutput(rows, many=True).data
        )
