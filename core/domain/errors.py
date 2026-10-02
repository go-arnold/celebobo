from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, ClassVar

_EMPTY: Mapping[str, Any] = MappingProxyType({})


class DomainError(Exception):
    default_code: ClassVar[str] = "domain_error"
    default_detail: ClassVar[str] = "La requête n'a pas pu être traitée."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        errors: Mapping[str, Sequence[str]] | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.default_detail
        self.code = code or self.default_code
        self.errors: Mapping[str, Sequence[str]] = errors or _EMPTY
        self.meta: Mapping[str, Any] = meta or _EMPTY
        super().__init__(self.detail)


class ValidationFailed(DomainError):
    default_code = "validation_failed"
    default_detail = "Les données envoyées sont invalides."


class Unauthenticated(DomainError):
    default_code = "not_authenticated"
    default_detail = "Authentification requise."


class Forbidden(DomainError):
    default_code = "forbidden"
    default_detail = "Vous n'avez pas la permission d'effectuer cette action."


class NotFound(DomainError):
    default_code = "not_found"
    default_detail = "Ressource introuvable."


class Conflict(DomainError):
    default_code = "conflict"
    default_detail = "Cette action entre en conflit avec l'état actuel de la ressource."


class BusinessRuleViolation(DomainError):
    default_code = "business_rule_violation"
    default_detail = "Cette action n'est pas autorisée par les règles métier."


class InvalidTransition(BusinessRuleViolation):
    default_code = "invalid_transition"
    default_detail = "Ce changement de statut n'est pas autorisé."


class InsufficientStock(BusinessRuleViolation):
    default_code = "insufficient_stock"
    default_detail = "Stock insuffisant."


class ServiceUnavailable(DomainError):
    default_code = "service_unavailable"
    default_detail = "Service momentanément indisponible. Réessayez plus tard."


class RateLimited(DomainError):
    default_code = "rate_limited"
    default_detail = "Trop de requêtes. Réessayez plus tard."
