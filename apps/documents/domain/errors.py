from datetime import datetime

from core.domain.errors import Conflict, NotFound, RateLimited, ValidationFailed


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


class ReceiptUnavailable(Conflict):
    default_code = "receipt_unavailable"
    default_detail = "Le reçu de livraison n'existe qu'une fois la commande livrée."


class JobExpired(NotFound):
    default_code = "job_expired"
    default_detail = "Ce lien de téléchargement a expiré. Demandez un nouvel export."


class PersonalDataExportTooSoon(RateLimited):
    default_code = "personal_data_export_too_soon"
    default_detail = "Vous avez déjà demandé vos données récemment. Réessayez plus tard."

    def __init__(self, available_at: datetime) -> None:
        super().__init__(meta={"available_at": available_at.isoformat()})
