from core.domain.errors import (
    BusinessRuleViolation,
    Conflict,
    Forbidden,
    NotFound,
    ValidationFailed,
)


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


class ItemNotAdjustable(BusinessRuleViolation):
    default_code = "item_not_adjustable"
    default_detail = "Le prix ne peut plus être modifié pour cette commande."


class InvalidProposedPrice(ValidationFailed):
    default_code = "invalid_proposed_price"
    default_detail = "Le prix proposé doit être positif et ne pas dépasser le prix catalogue."

    def __init__(self) -> None:
        super().__init__(errors={"new_price": [self.default_detail]})


class OrderItemNotFound(NotFound):
    default_code = "order_item_not_found"
    default_detail = "Article introuvable dans cette commande."


COUPON_MESSAGES = {
    "unknown": "Ce code promo n'existe pas.",
    "inactive": "Ce code promo n'est plus actif.",
    "not_started": "Ce code promo n'est pas encore valable.",
    "expired": "Ce code promo a expiré.",
    "minimum": "Le panier n'atteint pas le minimum requis pour ce code.",
    "exhausted": "Ce code promo a atteint sa limite d'utilisation.",
    "already_used": "Vous avez déjà utilisé ce code promo.",
    "login_required": "Connectez-vous pour utiliser ce code promo.",
}


class CouponRejected(ValidationFailed):
    default_code = "coupon_rejected"
    default_detail = "Ce code promo n'est pas valable."

    def __init__(self, reason: str, **meta: str) -> None:
        message = COUPON_MESSAGES[reason]
        super().__init__(
            message, errors={"coupon_code": [message]}, meta={"reason": reason, **meta}
        )


class ShippingZoneNotFound(NotFound):
    default_code = "shipping_zone_not_found"
    default_detail = "Zone de livraison introuvable."


class CouponNotFound(NotFound):
    default_code = "coupon_not_found"
    default_detail = "Code promo introuvable."


class CouponCodeTaken(Conflict):
    default_code = "coupon_code_taken"
    default_detail = "Un code promo utilise déjà ce code."
