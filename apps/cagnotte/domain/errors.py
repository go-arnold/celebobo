from core.domain.errors import BusinessRuleViolation, NotFound, ValidationFailed


class CampaignNotFound(NotFound):
    default_code = "campaign_not_found"
    default_detail = "Opération Cagnotte introuvable."


class RewardNotFound(NotFound):
    default_code = "reward_not_found"
    default_detail = "Avantage Cagnotte introuvable."


class InvalidCampaign(ValidationFailed):
    default_code = "invalid_campaign"
    default_detail = "Les conditions de l'opération sont invalides."

    def __init__(self, reason: str) -> None:
        super().__init__(detail=reason)


class CampaignOverlap(BusinessRuleViolation):
    default_code = "campaign_overlap"
    default_detail = "Une autre opération Cagnotte a lieu pendant ces dates : une seule à la fois."


class CampaignStarted(BusinessRuleViolation):
    default_code = "campaign_started"
    default_detail = (
        "L'opération a commencé : ses conditions ne changent plus, vous pouvez seulement y mettre "
        "fin."
    )


class CampaignEnded(BusinessRuleViolation):
    default_code = "campaign_ended"
    default_detail = "Cette opération Cagnotte est terminée."


class PointsDisabled(BusinessRuleViolation):
    default_code = "points_disabled"
    default_detail = (
        "Les points de fidélité sont désactivés : une opération payée en points n'est pas possible."
    )


class RewardNotDue(BusinessRuleViolation):
    default_code = "reward_not_due"
    default_detail = (
        "Ce cashback n'est pas à verser : délai d'essai en cours, déjà versé ou annulé."
    )
