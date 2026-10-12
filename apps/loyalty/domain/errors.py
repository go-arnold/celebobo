from core.domain.errors import BusinessRuleViolation, Conflict, NotFound


class ProgrammeClosed(BusinessRuleViolation):
    default_code = "membership_closed"
    default_detail = "L'abonnement Celebobo Plus n'est pas proposé pour le moment."


class TrialUnavailable(BusinessRuleViolation):
    default_code = "trial_unavailable"
    default_detail = "L'essai gratuit n'est pas disponible."

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail, meta={"reason": reason})


class RequestAlreadyPending(Conflict):
    default_code = "membership_request_pending"
    default_detail = "Une demande d'abonnement attend déjà la confirmation du paiement."


class MembershipRequestNotFound(NotFound):
    default_code = "membership_request_not_found"
    default_detail = "Demande d'abonnement introuvable."


class RequestAlreadyHandled(Conflict):
    default_code = "membership_request_handled"
    default_detail = "Cette demande a déjà été traitée."
