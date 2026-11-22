from collections.abc import Collection
from datetime import datetime

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.db.models import Max
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.loyalty.facades import PointsPrivacyFacade
from apps.messaging.facades import MessagingPrivacyFacade
from apps.orders.facades import OrderPrivacyFacade
from apps.push.facades import PushFacade
from core.container import container


# a session renewed with a refresh token counts as activity, as a login does
class SessionRenewals:
    def last_activity(self, user_ids: Collection[int]) -> dict[int, datetime]:
        rows = (
            OutstandingToken.objects.filter(user_id__in=list(user_ids), created_at__isnull=False)
            .values("user_id")
            .annotate(last=Max("created_at"))
        )
        return {row["user_id"]: row["last"] for row in rows}


# the e-mail addresses known to allauth and the Google link
class AllauthIdentities:
    def erase(self, user_id: int) -> None:
        EmailAddress.objects.filter(user_id=user_id).delete()
        SocialAccount.objects.filter(user_id=user_id).delete()


class OrdersPrivacy:
    def last_activity(self, user_ids: Collection[int]) -> dict[int, datetime]:
        return container.resolve(OrderPrivacyFacade).last_orders(user_ids)

    def erase(self, user_id: int) -> None:
        container.resolve(OrderPrivacyFacade).forget_client(user_id)


class MessagingPrivacy:
    def last_activity(self, user_ids: Collection[int]) -> dict[int, datetime]:
        return container.resolve(MessagingPrivacyFacade).last_messages(user_ids)

    def erase(self, user_id: int) -> None:
        container.resolve(MessagingPrivacyFacade).forget_client(user_id)


class LoyaltyPrivacy:
    def last_activity(self, user_ids: Collection[int]) -> dict[int, datetime]:
        return container.resolve(PointsPrivacyFacade).last_movements(user_ids)

    def erase(self, user_id: int) -> None:
        container.resolve(PointsPrivacyFacade).forget(user_id)


class PushDevices:
    def erase(self, user_id: int) -> None:
        container.resolve(PushFacade).forget(user_id)
