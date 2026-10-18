from core.domain.errors import BusinessRuleViolation, Conflict, NotFound


class ProgrammeClosed(BusinessRuleViolation):
    default_code = "loyalty_closed"
    default_detail = "Le programme de fidélité n'est pas proposé pour le moment."


class RuleNotFound(NotFound):
    default_code = "loyalty_rule_not_found"
    default_detail = "Règle de fidélité introuvable."


class CashbackUnavailable(Conflict):
    default_code = "cashback_unavailable"
    default_detail = "Votre cagnotte a changé. Mettez à jour votre commande."
