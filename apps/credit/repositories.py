from datetime import datetime

from django.db.models import QuerySet

from apps.credit.domain.rules import EntryKind
from apps.credit.models import CreditEntry


class CreditRepository:
    # issued credit with something left that has not expired yet
    def live(self, user_id: int, now: datetime) -> QuerySet[CreditEntry]:
        return CreditEntry.objects.filter(
            user_id=user_id, kind=EntryKind.ISSUED.value, remaining__gt=0, expires_at__gt=now
        )
