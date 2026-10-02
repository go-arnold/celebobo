from core.domain.errors import Conflict, NotFound, ValidationFailed


class JobNotFound(NotFound):
    default_code = "job_not_found"
    default_detail = "Tâche introuvable."


class JobNotReady(Conflict):
    default_code = "job_not_ready"
    default_detail = "Le fichier n'est pas encore disponible."


class UnsupportedFormat(ValidationFailed):
    default_code = "unsupported_format"
    default_detail = "Format non pris en charge pour ce document."

    def __init__(self) -> None:
        super().__init__(errors={"format": [self.default_detail]})


class InvalidImportFile(ValidationFailed):
    default_code = "invalid_import_file"
    default_detail = "Fichier d'import invalide."

    def __init__(self, reason: str) -> None:
        super().__init__(errors={"file": [reason]})


class InvoiceUnavailable(Conflict):
    default_code = "invoice_unavailable"
    default_detail = "La facture n'est pas disponible pour une commande annulée."
