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


class TooManyPendingOrders(BusinessRuleViolation):
    default_code = "too_many_pending_orders"
    default_detail = (
        "Vous avez déjà trop de commandes en attente. "
        "Attendez leur prise en charge ou annulez-en une."
    )

    def __init__(self, limit: int) -> None:
        super().__init__(meta={"limit": limit})


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


class LineNotReturnable(BusinessRuleViolation):
    default_code = "line_not_returnable"
    default_detail = "Seuls les articles d'une commande livrée peuvent être retournés."


class InvalidReturnQuantity(ValidationFailed):
    default_code = "invalid_return_quantity"
    default_detail = "Quantité à retourner invalide."

    def __init__(self, remaining: int) -> None:
        super().__init__(errors={"quantity": [self.default_detail]}, meta={"remaining": remaining})


class PickupUnavailable(ValidationFailed):
    default_code = "pickup_unavailable"
    default_detail = "Le retrait sur place n'est pas proposé pour le moment."

    def __init__(self) -> None:
        super().__init__(errors={"pickup": [self.default_detail]})


class ShippingNotQuotable(BusinessRuleViolation):
    default_code = "shipping_not_quotable"
    default_detail = "Les frais de livraison de cette commande ne sont pas à proposer."


class InvalidShippingQuote(ValidationFailed):
    default_code = "invalid_shipping_quote"
    default_detail = "Indiquez des frais de livraison valides."

    def __init__(self) -> None:
        super().__init__(errors={"fee": [self.default_detail]})


class NoRefundDue(BusinessRuleViolation):
    default_code = "no_refund_due"
    default_detail = "Aucun remboursement n'est attendu pour cette commande."


class DeliveryCodeRequired(ValidationFailed):
    default_code = "delivery_code_required"
    default_detail = "Saisissez le code de livraison que le client vous donne à la remise."

    def __init__(self) -> None:
        super().__init__(errors={"delivery_code": [self.default_detail]})


class InvalidDeliveryCode(BusinessRuleViolation):
    default_code = "invalid_delivery_code"
    default_detail = "Code de livraison incorrect."

    def __init__(self, attempts_left: int) -> None:
        super().__init__(meta={"attempts_left": attempts_left})


class DeliveryCodeLocked(BusinessRuleViolation):
    default_code = "delivery_code_locked"
    default_detail = (
        "Trop de codes incorrects : le code de livraison est bloqué. "
        "Un responsable doit confirmer la livraison."
    )


class DeliveryReasonRequired(ValidationFailed):
    default_code = "delivery_reason_required"
    default_detail = "Sans le code du client, indiquez pourquoi vous confirmez la livraison."

    def __init__(self) -> None:
        super().__init__(errors={"reason": [self.default_detail]})


class OrderNotRatable(BusinessRuleViolation):
    default_code = "order_not_ratable"
    default_detail = "Vous pourrez noter le revendeur une fois votre commande livrée."


class AlreadyRated(Conflict):
    default_code = "already_rated"
    default_detail = "Vous avez déjà noté le revendeur pour cette commande."


class AttemptNotAllowed(BusinessRuleViolation):
    default_code = "attempt_not_allowed"
    default_detail = (
        "Une tentative de livraison ne s'enregistre que pour une commande en livraison."
    )


class StoreCreditUnavailable(Conflict):
    default_code = "store_credit_unavailable"
    default_detail = "Votre avoir a changé. Vérifiez le montant puis confirmez."


class ResellerCashBlocked(BusinessRuleViolation):
    default_code = "reseller_cash_blocked"
    default_detail = (
        "Ce revendeur doit d'abord reverser l'argent encaissé : plus de 24 heures de retard ou "
        "plafond d'argent non reversé atteint."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(f"{self.default_detail} ({reason})", meta={"reason": reason})


class ResellerSuspended(BusinessRuleViolation):
    default_code = "reseller_suspended"
    default_detail = "Ce revendeur est suspendu : il ne reçoit pas de nouvelles commandes."

    def __init__(self, until: object) -> None:
        super().__init__(meta={"until": str(until)})


class PointsUnavailable(Conflict):
    default_code = "points_unavailable"
    default_detail = "Votre solde de points a changé. Vérifiez le montant puis confirmez."


class InvalidSerialNumber(ValidationFailed):
    default_code = "invalid_serial_number"
    default_detail = "Un numéro de série ou IMEI est invalide."


class TooManySerialNumbers(ValidationFailed):
    default_code = "too_many_serial_numbers"
    default_detail = "Il y a plus de numéros que d'unités sur cette ligne."


class SerialNumberAlreadySold(Conflict):
    default_code = "serial_number_already_sold"
    default_detail = "Ce numéro de série ou IMEI figure déjà sur une autre commande en cours."

    def __init__(self, serial: str, order_number: str) -> None:
        super().__init__(meta={"serial": serial, "order_number": order_number})


class SerialNumbersNotEditable(BusinessRuleViolation):
    default_code = "serial_numbers_not_editable"
    default_detail = (
        "Les numéros de série se saisissent avant la livraison ; après, seul un responsable peut "
        "les corriger."
    )


class SerialNumbersMissing(BusinessRuleViolation):
    default_code = "serial_numbers_missing"
    default_detail = (
        "Saisissez le numéro de série ou l'IMEI de chaque unité avant de faire partir la commande."
    )

    def __init__(self, lines: list[dict[str, object]]) -> None:
        super().__init__(meta={"lines": lines})
