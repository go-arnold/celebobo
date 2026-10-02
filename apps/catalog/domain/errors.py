from core.domain.errors import BusinessRuleViolation, NotFound, ServiceUnavailable


class ProductNotFound(NotFound):
    default_code = "product_not_found"
    default_detail = "Produit introuvable."


class CategoryNotFound(NotFound):
    default_code = "category_not_found"
    default_detail = "Catégorie introuvable."


class ReviewNotAllowed(BusinessRuleViolation):
    default_code = "review_not_allowed"
    default_detail = "Seuls les clients ayant reçu ce produit peuvent laisser un avis."


class SearchUnavailable(ServiceUnavailable):
    default_code = "search_unavailable"
    default_detail = "La recherche est momentanément indisponible."
