from core.domain.errors import BusinessRuleViolation, Conflict, NotFound, ValidationFailed


class SaleNotFound(NotFound):
    default_code = "sale_not_found"
    default_detail = "Vente introuvable."


class SaleNotEditable(BusinessRuleViolation):
    default_code = "sale_not_editable"
    default_detail = "Seules les ventes valides peuvent être modifiées."


class InvalidSaleDate(ValidationFailed):
    default_code = "invalid_sale_date"
    default_detail = "La date de vente ne peut pas être dans le futur."

    def __init__(self) -> None:
        super().__init__(errors={"sold_at": [self.default_detail]})


class SellerRequired(ValidationFailed):
    default_code = "seller_required"
    default_detail = "Indiquez le revendeur à qui attribuer la vente."

    def __init__(self) -> None:
        super().__init__(errors={"seller_id": [self.default_detail]})


class InvalidSeller(ValidationFailed):
    default_code = "invalid_seller"
    default_detail = "Ce vendeur est introuvable ou inactif."

    def __init__(self) -> None:
        super().__init__(errors={"seller_id": [self.default_detail]})


class RefundExceedsTotal(ValidationFailed):
    default_code = "refund_exceeds_total"
    default_detail = "Le montant dépasse ce qui reste remboursable."

    def __init__(self, refundable: str) -> None:
        super().__init__(errors={"amount": [self.default_detail]}, meta={"refundable": refundable})


class AlreadyReturned(BusinessRuleViolation):
    default_code = "already_returned"
    default_detail = "Cette vente a déjà été retournée."


class OrderNotConvertible(Conflict):
    default_code = "order_not_convertible"
    default_detail = "Cette commande ne peut pas être convertie en ventes."

    def __init__(self, reason: str) -> None:
        super().__init__(meta={"reason": reason})


class UnknownOrderItems(ValidationFailed):
    default_code = "unknown_order_items"
    default_detail = "Certains articles n'appartiennent pas à cette commande."

    def __init__(self) -> None:
        super().__init__(errors={"lines": [self.default_detail]})


class PayoutExceedsDue(ValidationFailed):
    default_code = "payout_exceeds_due"
    default_detail = "Le montant dépasse la commission due."

    def __init__(self, due: str) -> None:
        super().__init__(errors={"amount": [self.default_detail]}, meta={"due": due})


class NotAReseller(ValidationFailed):
    default_code = "not_a_reseller"
    default_detail = "Cet utilisateur n'est pas revendeur."

    def __init__(self) -> None:
        super().__init__(errors={"reseller_id": [self.default_detail]})


class ReturnThroughOrder(BusinessRuleViolation):
    default_code = "return_through_order"
    default_detail = "Cette vente provient d'une commande : enregistrez le retour sur la commande."
