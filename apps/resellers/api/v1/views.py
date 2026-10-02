from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.domain.commands import ResellerChanges, ResellerFilters
from apps.resellers.api.v1.serializers import (
    ApplicationFiltersInput,
    ApplicationOutput,
    ApplicationReceiptOutput,
    ApproveApplicationInput,
    InviteeOutput,
    InviteesSummaryOutput,
    ReferralKitOutput,
    RejectApplicationInput,
    ResellerChangesInput,
    ResellerFiltersInput,
    ResellerOutput,
    ResellerStatsOutput,
    SubmitApplicationInput,
)
from apps.resellers.domain.commands import (
    ApplicationFilters,
    ApproveApplication,
    RejectApplication,
    SubmitApplication,
)
from apps.resellers.domain.read_models import InviteesPage
from apps.resellers.facades import ApplicationFacade, ReferralFacade, ResellerProgramFacade
from apps.resellers.permissions import (
    APPLICATIONS_REVIEW,
    REFERRAL_VIEW_OWN,
    RESELLERS_MANAGE,
    RESELLERS_VIEW,
)
from core.api.pagination import PageRequest, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


def invitees_response(
    request: Request, page: PageRequest, result: InviteesPage, total: int
) -> Response:
    return page_response(
        request,
        page,
        total=total,
        results=InviteeOutput(result.invitees, many=True).data,
        meta={"summary": InviteesSummaryOutput(result).data},
    )


class ApplicationSubmissionViewSet(UseCaseViewSet):
    permission_classes = (AllowAny,)
    throttle_scope = "reseller_applications"
    applications = Inject(ApplicationFacade)

    @extend_schema(request=SubmitApplicationInput, responses={201: ApplicationReceiptOutput})
    def create(self, request: Request) -> Response:
        command = self.parse(SubmitApplicationInput, into=SubmitApplication)
        application = self.applications.submit(self.actor, command)
        return self.respond(ApplicationReceiptOutput, application, status=201)


class ApplicationReviewViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (APPLICATIONS_REVIEW,),
        "retrieve": (APPLICATIONS_REVIEW,),
        "approve": (APPLICATIONS_REVIEW,),
        "reject": (APPLICATIONS_REVIEW,),
    }
    applications = Inject(ApplicationFacade)

    @extend_schema(parameters=[ApplicationFiltersInput], responses=ApplicationOutput(many=True))
    def list(self, request: Request) -> Response:
        filters = self.parse(
            ApplicationFiltersInput, into=ApplicationFilters, data=request.query_params
        )
        page = page_request(request, default_size=20, max_size=100)
        applications, total, counts = self.applications.page(
            filters, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request,
            page,
            total=total,
            results=ApplicationOutput(applications, many=True).data,
            meta={"counts": counts},
        )

    @extend_schema(responses=ApplicationOutput)
    def retrieve(self, request: Request, application_id: int) -> Response:
        return self.respond(ApplicationOutput, self.applications.detail(application_id))

    @extend_schema(request=ApproveApplicationInput, responses=ApplicationOutput)
    def approve(self, request: Request, application_id: int) -> Response:
        command = self.parse(ApproveApplicationInput, into=ApproveApplication)
        return self.respond(
            ApplicationOutput, self.applications.approve(self.actor, application_id, command)
        )

    @extend_schema(request=RejectApplicationInput, responses=ApplicationOutput)
    def reject(self, request: Request, application_id: int) -> Response:
        command = self.parse(RejectApplicationInput, into=RejectApplication)
        return self.respond(
            ApplicationOutput, self.applications.reject(self.actor, application_id, command)
        )


class ResellerViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (RESELLERS_VIEW,),
        "stats": (RESELLERS_VIEW,),
        "retrieve": (RESELLERS_VIEW,),
        "invitees": (RESELLERS_VIEW,),
        "partial_update": (RESELLERS_MANAGE,),
        "activate": (RESELLERS_MANAGE,),
        "deactivate": (RESELLERS_MANAGE,),
    }
    program = Inject(ResellerProgramFacade)

    @extend_schema(parameters=[ResellerFiltersInput], responses=ResellerOutput(many=True))
    def list(self, request: Request) -> Response:
        filters = self.parse(ResellerFiltersInput, into=ResellerFilters, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        resellers, total = self.program.page(filters, offset=page.offset, limit=page.page_size)
        return page_response(
            request, page, total=total, results=ResellerOutput(resellers, many=True).data
        )

    @extend_schema(responses=ResellerStatsOutput)
    def stats(self, request: Request) -> Response:
        return self.respond(ResellerStatsOutput, self.program.stats())

    @extend_schema(responses=ResellerOutput)
    def retrieve(self, request: Request, reseller_id: int) -> Response:
        return self.respond(ResellerOutput, self.program.detail(reseller_id))

    @extend_schema(request=ResellerChangesInput, responses=ResellerOutput)
    def partial_update(self, request: Request, reseller_id: int) -> Response:
        changes = self.parse(ResellerChangesInput, into=ResellerChanges, partial=True)
        return self.respond(ResellerOutput, self.program.update(self.actor, reseller_id, changes))

    @extend_schema(request=None, responses=ResellerOutput)
    def activate(self, request: Request, reseller_id: int) -> Response:
        return self.respond(
            ResellerOutput, self.program.set_active(self.actor, reseller_id, active=True)
        )

    @extend_schema(request=None, responses=ResellerOutput)
    def deactivate(self, request: Request, reseller_id: int) -> Response:
        return self.respond(
            ResellerOutput, self.program.set_active(self.actor, reseller_id, active=False)
        )

    @extend_schema(responses=InviteeOutput(many=True))
    def invitees(self, request: Request, reseller_id: int) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        result, total = self.program.invitees(reseller_id, offset=page.offset, limit=page.page_size)
        return invitees_response(request, page, result, total)


class ReferralViewSet(UseCaseViewSet):
    action_permissions = {"retrieve": (REFERRAL_VIEW_OWN,), "invitees": (REFERRAL_VIEW_OWN,)}
    referrals = Inject(ReferralFacade)

    @extend_schema(responses=ReferralKitOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(ReferralKitOutput, self.referrals.kit(self.actor))

    @extend_schema(responses=InviteeOutput(many=True))
    def invitees(self, request: Request) -> Response:
        page = page_request(request, default_size=20, max_size=100)
        result, total = self.referrals.invitees(
            self.actor, offset=page.offset, limit=page.page_size
        )
        return invitees_response(request, page, result, total)
