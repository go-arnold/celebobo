from core.domain.errors import (
    BusinessRuleViolation,
    Conflict,
    InsufficientStock,
    NotFound,
    ValidationFailed,
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


class InvalidPricing(ValidationFailed):
    default_code = "invalid_pricing"
    default_detail = "Les prix du produit sont incohérents."

    def __init__(self, errors: dict[str, list[str]]) -> None:
        super().__init__(errors=errors)


class SellByInPast(ValidationFailed):
    default_code = "sell_by_in_past"
    default_detail = "La date limite de vente ne peut pas être passée."

    def __init__(self) -> None:
        super().__init__(errors={"sell_by": [self.default_detail]})


class CategoryNameTaken(ValidationFailed):
    default_code = "category_name_taken"
    default_detail = "Une catégorie porte déjà ce nom."

    def __init__(self) -> None:
        super().__init__(errors={"name": [self.default_detail]})


class CategoryNotEmpty(Conflict):
    default_code = "category_not_empty"
    default_detail = "Cette catégorie contient encore des produits. Choisissez où les déplacer."

    def __init__(self, products_count: int) -> None:
        super().__init__(meta={"products_count": products_count})


class InvalidVariantAttributes(ValidationFailed):
    default_code = "invalid_variant_attributes"
    default_detail = "Les attributs de la variante sont invalides."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail, errors={"attributes": [detail or self.default_detail]})


class DuplicateSku(ValidationFailed):
    default_code = "duplicate_sku"
    default_detail = "Ce SKU est déjà utilisé."

    def __init__(self) -> None:
        super().__init__(errors={"sku": [self.default_detail]})


class DuplicateVariant(ValidationFailed):
    default_code = "duplicate_variant"
    default_detail = "Une variante avec ces attributs existe déjà."

    def __init__(self) -> None:
        super().__init__(errors={"attributes": [self.default_detail]})


class VariantNotFound(NotFound):
    default_code = "variant_not_found"
    default_detail = "Variante introuvable."


class VariantsManageStock(BusinessRuleViolation):
    default_code = "variants_manage_stock"
    default_detail = "Le stock de ce produit se gère par variante."


class NegativeStock(BusinessRuleViolation):
    default_code = "negative_stock"
    default_detail = "Le stock ne peut pas devenir négatif."


class UnknownImages(ValidationFailed):
    default_code = "unknown_images"
    default_detail = "Certaines images sont introuvables. Téléversez-les d'abord."

    def __init__(self, field: str = "image_ids") -> None:
        super().__init__(errors={field: [self.default_detail]})


class ReviewNotFound(NotFound):
    default_code = "review_not_found"
    default_detail = "Avis introuvable."
