from core.domain.errors import Conflict, NotFound, ValidationFailed


class ContactMessageNotFound(NotFound):
    default_code = "contact_message_not_found"
    default_detail = "Message introuvable."


class PageNotFound(NotFound):
    default_code = "page_not_found"
    default_detail = "Page introuvable."


class FaqEntryNotFound(NotFound):
    default_code = "faq_entry_not_found"
    default_detail = "Question introuvable."


class BannerNotFound(NotFound):
    default_code = "banner_not_found"
    default_detail = "Bannière introuvable."


class SlugTaken(Conflict):
    default_code = "slug_taken"
    default_detail = "Une page utilise déjà cette adresse."


class UnknownSubscription(NotFound):
    default_code = "unknown_subscription"
    default_detail = "Lien de désinscription invalide."


class InvalidSchedule(ValidationFailed):
    default_code = "invalid_schedule"
    default_detail = "La fin doit suivre le début."

    def __init__(self) -> None:
        super().__init__(errors={"ends_at": [self.default_detail]})


class UnknownPaymentMethod(ValidationFailed):
    default_code = "unknown_payment_method"
    default_detail = "Moyen de paiement inconnu."

    def __init__(self, method: str) -> None:
        super().__init__(errors={"payment_methods": [f"Inconnu : {method}."]})
