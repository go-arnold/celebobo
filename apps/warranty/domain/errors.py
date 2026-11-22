from core.domain.errors import BusinessRuleViolation, Conflict, NotFound, ValidationFailed


class ClaimNotFound(NotFound):
    default_code = "claim_not_found"
    default_detail = "Réclamation introuvable."


class LineNotClaimable(NotFound):
    default_code = "line_not_claimable"
    default_detail = "Cet article ne fait pas partie de vos commandes."


class ClaimWindowClosed(BusinessRuleViolation):
    default_code = "claim_window_closed"
    default_detail = (
        "Le délai est dépassé : changement d'avis pendant les 7 jours d'essai, défaut pendant "
        "l'essai ou le mois de garantie, contrefaçon dans les 12 mois suivant l'achat."
    )


class ClaimAlreadyOpen(Conflict):
    default_code = "claim_already_open"
    default_detail = "Une réclamation est déjà en cours pour cet article."


class SerialNotOnOrder(ValidationFailed):
    default_code = "serial_not_on_order"
    default_detail = "Ce numéro de série ou IMEI ne figure pas sur la facture de cette commande."


class ClaimStepNotAllowed(BusinessRuleViolation):
    default_code = "claim_step_not_allowed"
    default_detail = "Cette étape ne correspond pas à l'état de la réclamation."


class OutcomeNotAllowed(BusinessRuleViolation):
    default_code = "outcome_not_allowed"
    default_detail = "Cette solution n'est pas possible pour cette réclamation."


class SealRequired(BusinessRuleViolation):
    default_code = "seal_required"
    default_detail = (
        "Ce produit n'est repris pour un changement d'avis que sous scellé : le scellé n'était pas "
        "intact à la réception."
    )
