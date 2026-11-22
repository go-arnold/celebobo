from typing import TYPE_CHECKING

from rest_framework.permissions import BasePermission

from core.api.actor import actor_from_user
from core.container import container
from core.domain.actor import Actor

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class AccountComplete(BasePermission):
    """A client or reseller who still has required consents to give, or no phone number, cannot
    use the account.

    Default permission of every authenticated endpoint. A view sets `allow_incomplete_account`
    to stay reachable during the completion step (profile, consents); public views (catalogue,
    policy pages) and the session endpoints (login, logout, refresh) do not use the default
    permissions and are not affected.
    """

    def has_permission(self, request: "Request", view: "APIView") -> bool:
        # imported here: DRF loads this class while `rest_framework.views` is still initialising
        from apps.accounts.domain.errors import AccountIncomplete
        from apps.accounts.domain.phone import phone_missing
        from apps.accounts.selectors import ConsentSelector

        if getattr(view, "allow_incomplete_account", False):
            return True
        actor = getattr(view, "actor", None)
        if not isinstance(actor, Actor):
            actor = actor_from_user(request.user)
        if actor.user_id is None:
            return True
        missing = container.resolve(ConsentSelector).missing(actor.user_id, actor.role)
        no_phone = phone_missing(actor.role, getattr(request.user, "phone_number", None))
        if missing or no_phone:
            raise AccountIncomplete(
                missing_consents=[kind.value for kind in missing], phone_required=no_phone
            )
        return True
