from core.domain.errors import NotFound


class AuditEntryNotFound(NotFound):
    default_code = "audit_entry_not_found"
    default_detail = "Entrée du journal introuvable."
