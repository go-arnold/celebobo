from core.domain.errors import BusinessRuleViolation, Forbidden, NotFound, ValidationFailed


class OrderNotFound(NotFound):
    default_code = "order_not_found"
    default_detail = "Commande introuvable."


class EmptyOrder(ValidationFailed):
    default_code = "empty_order"
    default_detail = "Votre commande ne contient aucun article."

    def __init__(self) -> None:
        super().__init__(errors={"items": [self.default_detail]})


class TooManyLines(ValidationFailed):
    default_code = "too_many_lines"
    default_detail = "Votre commande contient trop d'articles différents."

    def __init__(self, limit: int) -> None:
        super().__init__(errors={"items": [self.default_detail]}, meta={"limit": limit})


class AddressRequired(ValidationFailed):
    default_code = "address_required"
    default_detail = "Indiquez une adresse de livraison."

    def __init__(self) -> None:
        super().__init__(errors={"address": [self.default_detail]})


class ResellerNotFound(ValidationFailed):
    default_code = "reseller_not_found"
    default_detail = "Revendeur introuvable ou inactif."

    def __init__(self) -> None:
        super().__init__(errors={"reseller_id": [self.default_detail]})


class AssignmentClosed(BusinessRuleViolation):
    default_code = "assignment_closed"
    default_detail = "Cette commande ne peut plus être réassignée."


class NotAssignedToYou(Forbidden):
    default_code = "not_assigned_to_you"
    default_detail = "Cette commande ne vous est pas assignée."


class CartLineNotFound(NotFound):
    default_code = "cart_line_not_found"
    default_detail = "Article introuvable dans le panier."
