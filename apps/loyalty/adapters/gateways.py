from django.utils import timezone

from apps.accounts.selectors import ProfileSelector
from apps.loyalty.domain.membership import Requester
from apps.loyalty.repositories import MembershipRepository
from core.authz.catalog import permission_catalog


class AccountsPeople:
    def requester(self, user_id: int) -> Requester:
        profile = ProfileSelector(permission_catalog).profile(user_id)
        name = f"{profile.first_name} {profile.last_name}".strip() or profile.email
        return Requester(
            id=profile.id,
            name=name,
            email_verified=profile.email_verified,
            phone=profile.phone_number,
        )


class LoyaltyMembers:
    def is_member(self, user_id: int) -> bool:
        return MembershipRepository().active(user_id, timezone.now())
