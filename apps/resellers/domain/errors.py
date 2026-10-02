from core.domain.errors import Conflict, NotFound


class ApplicationNotFound(NotFound):
    default_code = "application_not_found"
    default_detail = "Candidature introuvable."


class ApplicationPending(Conflict):
    default_code = "application_pending"
    default_detail = "Une candidature est déjà en cours d'examen pour cette adresse e-mail."


class AlreadyReseller(Conflict):
    default_code = "already_reseller"
    default_detail = "Cette adresse e-mail appartient déjà à un revendeur."


class ApplicationReviewed(Conflict):
    default_code = "application_reviewed"
    default_detail = "Cette candidature a déjà été traitée."


class NoReferralCode(NotFound):
    default_code = "no_referral_code"
    default_detail = "Aucun code revendeur n'est associé à votre compte."
