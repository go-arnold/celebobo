from typing import Any

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.jwt_auth import set_jwt_cookies, unset_jwt_cookies
from dj_rest_auth.registration.views import SocialLoginView
from dj_rest_auth.utils import jwt_encode
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.api.v1.serializers import (
    AddressInput,
    AddressOutput,
    AddressPatchInput,
    AvailabilityInput,
    ChangeRoleInput,
    PreferencesInput,
    PreferencesOutput,
    ProfileOutput,
    ReferralCheckOutput,
    RegisterInput,
    RegistrationOutput,
    UpdateProfileInput,
    WsTicketOutput,
)
from apps.accounts.domain.commands import (
    AddressChanges,
    AddressFields,
    ChangeRole,
    RegisterUser,
    SetAvailability,
    UpdatePreferences,
    UpdateProfile,
)
from apps.accounts.facades import (
    AccountFacade,
    AddressBookFacade,
    PreferencesFacade,
    RealtimeAccessFacade,
)
from apps.accounts.models import User
from apps.accounts.permissions import (
    ACCOUNT_DELETE,
    ACCOUNT_UPDATE,
    ACCOUNT_VIEW,
    ADDRESSES_MANAGE,
    AVAILABILITY_UPDATE,
    PREFERENCES_MANAGE,
    REALTIME_CONNECT,
    USERS_MANAGE,
)
from apps.accounts.selectors import AddressSelector, ProfileSelector, ReferralSelector
from core.api.views import UseCaseViewSet
from core.authz.catalog import permission_catalog
from core.container import Inject

ADDRESS_PERMISSIONS = (ADDRESSES_MANAGE,)


class RegisterViewSet(UseCaseViewSet):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth"
    accounts = Inject(AccountFacade)

    @extend_schema(request=RegisterInput, responses={201: RegistrationOutput})
    def create(self, request: Request) -> Response:
        registration = self.accounts.register(self.parse(RegisterInput, into=RegisterUser))
        response = self.respond(RegistrationOutput, registration, status=201)
        if not registration.verification_required:
            access, refresh = jwt_encode(User.objects.get(pk=registration.user_id))
            set_jwt_cookies(response, access, refresh)
        return response


class MeViewSet(UseCaseViewSet):
    action_permissions = {
        "retrieve": (ACCOUNT_VIEW,),
        "partial_update": (ACCOUNT_UPDATE,),
        "destroy": (ACCOUNT_DELETE,),
    }
    accounts = Inject(AccountFacade)
    profiles = ProfileSelector(permission_catalog)

    @extend_schema(responses=ProfileOutput)
    def retrieve(self, request: Request) -> Response:
        return self.respond(ProfileOutput, self.profiles.profile(self.user_id()))

    @extend_schema(request=UpdateProfileInput, responses=ProfileOutput)
    def partial_update(self, request: Request) -> Response:
        command = self.parse(UpdateProfileInput, into=UpdateProfile, partial=True)
        return self.respond(ProfileOutput, self.accounts.update_profile(self.actor, command))

    @extend_schema(responses={204: None})
    def destroy(self, request: Request) -> Response:
        self.accounts.delete_account(self.actor)
        response = Response(status=204)
        unset_jwt_cookies(response)
        return response


class AddressViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "create", "partial_update", "destroy", "set_default"), ADDRESS_PERMISSIONS
    )
    lookup_value_converter = "int"
    book = Inject(AddressBookFacade)
    addresses = AddressSelector()

    @extend_schema(responses=AddressOutput(many=True))
    def list(self, request: Request) -> Response:
        return self.respond(AddressOutput, self.addresses.for_user(self.user_id()), many=True)

    @extend_schema(request=AddressInput, responses={201: AddressOutput})
    def create(self, request: Request) -> Response:
        fields = self.parse(AddressInput, into=AddressFields)
        return self.respond(AddressOutput, self.book.add(self.actor, fields), status=201)

    @extend_schema(request=AddressPatchInput, responses=AddressOutput)
    def partial_update(self, request: Request, pk: int) -> Response:
        changes = self.parse(AddressPatchInput, into=AddressChanges, partial=True)
        return self.respond(AddressOutput, self.book.update(self.actor, pk, changes))

    @extend_schema(responses={204: None})
    def destroy(self, request: Request, pk: int) -> Response:
        self.book.remove(self.actor, pk)
        return Response(status=204)

    @extend_schema(request=None, responses=AddressOutput)
    @action(detail=True, methods=["post"], url_path="set-default")
    def set_default(self, request: Request, pk: int) -> Response:
        return self.respond(AddressOutput, self.book.set_default(self.actor, pk))


class PreferencesViewSet(UseCaseViewSet):
    action_permissions = {
        "retrieve": (PREFERENCES_MANAGE,),
        "partial_update": (PREFERENCES_MANAGE,),
    }
    preferences = Inject(PreferencesFacade)

    @extend_schema(responses=PreferencesOutput)
    def retrieve(self, request: Request) -> Response:
        return Response(self.preferences.current(self.actor))

    @extend_schema(request=PreferencesInput, responses=PreferencesOutput)
    def partial_update(self, request: Request) -> Response:
        command = self.parse(PreferencesInput, into=UpdatePreferences)
        return Response(self.preferences.update(self.actor, command))


class ReferralCodeViewSet(UseCaseViewSet):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "referral"
    referrals = ReferralSelector()

    @extend_schema(responses=ReferralCheckOutput)
    def retrieve(self, request: Request, code: str) -> Response:
        return self.respond(ReferralCheckOutput, self.referrals.check(code))


class WsTicketViewSet(UseCaseViewSet):
    action_permissions = {"create": (REALTIME_CONNECT,)}
    realtime = Inject(RealtimeAccessFacade)

    @extend_schema(request=None, responses={201: WsTicketOutput})
    def create(self, request: Request) -> Response:
        return self.respond(WsTicketOutput, self.realtime.issue_ticket(self.actor), status=201)


@method_decorator(ensure_csrf_cookie, name="retrieve")
class CsrfViewSet(UseCaseViewSet):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(responses={204: None})
    def retrieve(self, request: Request) -> Response:
        return Response(status=204)


class UserRoleViewSet(UseCaseViewSet):
    action_permissions = {"create": (USERS_MANAGE,)}
    accounts = Inject(AccountFacade)

    @extend_schema(request=ChangeRoleInput, responses=ProfileOutput)
    def create(self, request: Request, user_id: int) -> Response:
        command = self.parse(ChangeRoleInput, into=ChangeRole, user_id=user_id)
        return self.respond(ProfileOutput, self.accounts.change_role(self.actor, command))


class AvailabilityViewSet(UseCaseViewSet):
    action_permissions = {"partial_update": (AVAILABILITY_UPDATE,)}
    accounts = Inject(AccountFacade)

    @extend_schema(request=AvailabilityInput, responses=ProfileOutput)
    def partial_update(self, request: Request) -> Response:
        command = self.parse(AvailabilityInput, into=SetAvailability)
        return self.respond(ProfileOutput, self.accounts.set_availability(self.actor, command))


class GoogleLoginView(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    throttle_scope = "auth"

    @property
    def callback_url(self) -> Any:
        return settings.GOOGLE_OAUTH_CALLBACK_URL
