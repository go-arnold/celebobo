from core.domain.errors import (
    BusinessRuleViolation,
    InsufficientStock,
    NotFound,
)


class ProductNotFound(NotFound):
    default_code = "product_not_found"
    default_detail = "Produit introuvable."


class CategoryNotFound(NotFound):
    default_code = "category_not_found"
    default_detail = "Catégorie introuvable."


class ReviewNotAllowed(BusinessRuleViolation):
    default_code = "review_not_allowed"
    default_detail = "Seuls les clients ayant reçu ce produit peuvent laisser un avis."


class ProductUnavailable(BusinessRuleViolation):
    default_code = "product_unavailable"
    default_detail = "Ce produit n'est plus disponible."

    def __init__(self, product_id: int) -> None:
        super().__init__(meta={"product_id": product_id})


class VariantRequired(BusinessRuleViolation):
    default_code = "variant_required"
    default_detail = "Choisissez une variante pour ce produit."

    def __init__(self, product_id: int) -> None:
        super().__init__(meta={"product_id": product_id})


class OutOfStock(InsufficientStock):
    default_code = "insufficient_stock"

    def __init__(self, product_id: int, *, variant_id: int | None, available: int) -> None:
        super().__init__(
            f"Stock insuffisant ({available} disponible{'s' if available > 1 else ''}).",
            meta={"product_id": product_id, "variant_id": variant_id, "available": available},
        )
