from core.domain.errors import BusinessRuleViolation, NotFound


class NotAReseller(NotFound):
    default_code = "not_a_reseller"
    default_detail = "Ce compte n'est pas un revendeur."


class RemittanceExceedsHeld(BusinessRuleViolation):
    default_code = "remittance_exceeds_held"
    default_detail = "Le montant dépasse l'argent que ce revendeur doit reverser."

    def __init__(self, held: str) -> None:
        super().__init__(meta={"held": held})
