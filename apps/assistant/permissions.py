from core.authz.catalog import permission_catalog
from core.domain.actor import Role

ASSISTANT_CHAT = "assistant.chat"
ASSISTANT_HISTORY = "assistant.history"
ASSISTANT_LOGS = "assistant.logs"
EMBEDDINGS_REINDEX = "embeddings.reindex"

permission_catalog.grant(Role.ANONYMOUS, ASSISTANT_CHAT)
permission_catalog.grant(Role.CLIENT, ASSISTANT_HISTORY)
permission_catalog.grant(Role.MANAGER, ASSISTANT_LOGS)
permission_catalog.grant(Role.ADMIN, EMBEDDINGS_REINDEX)
