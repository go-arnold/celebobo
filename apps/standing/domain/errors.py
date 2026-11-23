from core.domain.errors import BusinessRuleViolation, NotFound, ValidationFailed


class SanctionNotFound(NotFound):
    default_code = "sanction_not_found"
    default_detail = "Sanction introuvable."


class NotAReseller(NotFound):
    default_code = "not_a_reseller"
    default_detail = "Ce compte n'est pas un revendeur."


class InvalidSuspension(ValidationFailed):
    default_code = "invalid_suspension"
    default_detail = "Une suspension dure de 7 à 30 jours."


class SanctionClosed(BusinessRuleViolation):
    default_code = "sanction_closed"
    default_detail = "Cette sanction est déjà décidée."


class ExplanationClosed(BusinessRuleViolation):
    default_code = "explanation_closed"
    default_detail = "Le délai de 48 heures pour vous expliquer est passé."


class HearingPending(BusinessRuleViolation):
    default_code = "hearing_pending"
    default_detail = (
        "Le revendeur peut encore s'expliquer : attendez sa réponse ou la fin des 48 heures."
    )
