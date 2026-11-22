from collections.abc import Sequence
from datetime import datetime

from apps.audit.domain.retention import BATCH_SIZE, RetentionReport, years_before
from apps.audit.services.retention import purge_expired
from apps.messaging.domain.retention import CONVERSATION_RETENTION_YEARS, StaleConversation
from apps.messaging.repositories import ConversationRepository
from apps.messaging.services.contracts import OrderGateway

RULE = "messaging.stale_conversations"


class StaleConversationRetention:
    label = "Discussions sans message ni commande du client depuis 3 ans, supprimées"

    def __init__(self, conversations: ConversationRepository, orders: OrderGateway) -> None:
        self._conversations = conversations
        self._orders = orders

    def apply(self, *, now: datetime, dry_run: bool) -> RetentionReport:
        cutoff = years_before(now, CONVERSATION_RETENTION_YEARS)

        def ordered_since(batch: Sequence[StaleConversation]) -> set[int]:
            last = self._orders.last_orders({row.client_id for row in batch})
            return {
                row.id
                for row in batch
                if (ordered := last.get(row.client_id)) is not None and ordered >= cutoff
            }

        return purge_expired(
            rule=RULE,
            label=self.label,
            fetch=lambda after: self._conversations.stale_before(
                cutoff, after_id=after, limit=BATCH_SIZE
            ),
            keep=ordered_since,
            delete=lambda ids: self._conversations.delete_stale(ids, before=cutoff),
            dry_run=dry_run,
        )
