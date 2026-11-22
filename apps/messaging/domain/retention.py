from dataclasses import dataclass

from apps.audit.domain.retention import Expired

# privacy policy, section 6: messages with customer service or the reseller are kept 3 years
# after the client's last order. Per discussion: deleted (with its messages, proposals and
# notifications) once its last message (or its opening, without any) is more than 3 years old
# and the client has placed no order for 3 years either.
CONVERSATION_RETENTION_YEARS = 3


@dataclass(frozen=True, slots=True)
class StaleConversation(Expired):
    client_id: int
