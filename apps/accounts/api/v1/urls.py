from dj_rest_auth.jwt_auth import get_refresh_view
from dj_rest_auth.registration.views import ResendEmailVerificationView, VerifyEmailView
from dj_rest_auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.accounts.api.v1.backoffice_views import UserAdminViewSet
from apps.accounts.api.v1.views import (
    AddressViewSet,
    AvailabilityViewSet,
    CsrfViewSet,
    GoogleLoginView,
    MeViewSet,
    PreferencesViewSet,
    ReferralCodeViewSet,
    RegisterViewSet,
    UserRoleViewSet,
    WsTicketViewSet,
)

addresses = SimpleRouter(use_regex_path=False)
addresses.register("me/addresses", AddressViewSet, basename="address")

auth_patterns = [
    path("register/", RegisterViewSet.as_view({"post": "create"}), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", get_refresh_view().as_view(), name="token-refresh"),
    path("csrf/", CsrfViewSet.as_view({"get": "retrieve"}), name="csrf"),
    path("email/verify/", VerifyEmailView.as_view(), name="email-verify"),
    path("email/resend/", ResendEmailVerificationView.as_view(), name="email-resend"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("social/google/", GoogleLoginView.as_view(), name="social-google"),
    path(
        "referral-codes/<str:code>/validate/",
        ReferralCodeViewSet.as_view({"get": "retrieve"}),
        name="referral-validate",
    ),
    path("ws-ticket/", WsTicketViewSet.as_view({"post": "create"}), name="ws-ticket"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path(
        "me/",
        MeViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="me",
    ),
    path(
        "me/notification-preferences/",
        PreferencesViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="notification-preferences",
    ),
    path(
        "bo/users/",
        UserAdminViewSet.as_view({"get": "list", "post": "create"}),
        name="bo-users",
    ),
    path(
        "bo/users/<int:user_id>/",
        UserAdminViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="bo-user",
    ),
    path(
        "bo/users/<int:user_id>/activate/",
        UserAdminViewSet.as_view({"post": "activate"}),
        name="bo-user-activate",
    ),
    path(
        "bo/users/<int:user_id>/deactivate/",
        UserAdminViewSet.as_view({"post": "deactivate"}),
        name="bo-user-deactivate",
    ),
    path(
        "bo/users/<int:user_id>/send-password-reset/",
        UserAdminViewSet.as_view({"post": "send_password_reset"}),
        name="bo-user-password-reset",
    ),
    path(
        "bo/users/<int:user_id>/role/",
        UserRoleViewSet.as_view({"post": "create"}),
        name="user-role",
    ),
    path(
        "bo/me/availability/",
        AvailabilityViewSet.as_view({"patch": "partial_update"}),
        name="availability",
    ),
    *addresses.urls,
]
