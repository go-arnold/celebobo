from core.authz.catalog import permission_catalog
from core.domain.actor import Role

CONVERSATIONS_USE = "conversations.use"
CONVERSATIONS_OPEN_SUPPORT = "conversations.open_support"
CONVERSATIONS_RESPOND_PROPOSAL = "conversations.respond_proposal"
NOTIFICATIONS_VIEW = "notifications.view"
CONVERSATIONS_MODERATE = "conversations.moderate"
PRICE_ADJUST = "price.adjust"
CONVERSATIONS_ASSIGN = "conversations.assign"

permission_catalog.grant(
    Role.CLIENT,
    CONVERSATIONS_USE,
    CONVERSATIONS_OPEN_SUPPORT,
    CONVERSATIONS_RESPOND_PROPOSAL,
    NOTIFICATIONS_VIEW,
)
permission_catalog.grant(Role.RESELLER, CONVERSATIONS_MODERATE, PRICE_ADJUST)
permission_catalog.grant(Role.MANAGER, CONVERSATIONS_ASSIGN)
