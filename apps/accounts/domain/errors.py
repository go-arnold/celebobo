from core.domain.errors import (
    BusinessRuleViolation,
    Forbidden,
    NotFound,
    ServiceUnavailable,
    ValidationFailed,
)


class EmailAlreadyUsed(ValidationFailed):
    default_code = "email_already_used"
    default_detail = "Un compte existe déjà avec cette adresse e-mail."

    def __init__(self) -> None:
        super().__init__(errors={"email": [self.default_detail]})


class PhoneAlreadyUsed(ValidationFailed):
    default_code = "phone_already_used"
    default_detail = "Ce numéro de téléphone est déjà utilisé."

    def __init__(self) -> None:
        super().__init__(errors={"phone_number": [self.default_detail]})


class UnknownReferralCode(ValidationFailed):
    default_code = "unknown_referral_code"
    default_detail = "Aucun revendeur trouvé avec ce code."

    def __init__(self) -> None:
        super().__init__(errors={"referral_code": [self.default_detail]})


class WeakPassword(ValidationFailed):
    default_code = "weak_password"
    default_detail = "Le mot de passe ne respecte pas les règles de sécurité."

    def __init__(self, messages: list[str]) -> None:
        super().__init__(errors={"password": messages})


class ReferralAlreadySet(BusinessRuleViolation):
    default_code = "referral_already_set"
    default_detail = "Un code revendeur est déjà associé à votre compte."


class SelfReferral(BusinessRuleViolation):
    default_code = "self_referral"
    default_detail = "Vous ne pouvez pas utiliser votre propre code revendeur."


class ReferralCodesExhausted(ServiceUnavailable):
    default_code = "referral_codes_exhausted"
    default_detail = "Impossible de générer un code revendeur pour le moment."


class AddressBookFull(BusinessRuleViolation):
    default_code = "address_book_full"
    default_detail = "Vous avez atteint le nombre maximal d'adresses."


class AddressNotFound(NotFound):
    default_code = "address_not_found"
    default_detail = "Adresse introuvable."


class UserNotFound(NotFound):
    default_code = "user_not_found"
    default_detail = "Utilisateur introuvable."


class StaffAccountDeletion(BusinessRuleViolation):
    default_code = "staff_account_deletion"
    default_detail = (
        "Les comptes revendeur et administrateur doivent être désactivés par un administrateur."
    )


class OwnRoleChange(Forbidden):
    default_code = "own_role_change"
    default_detail = "Vous ne pouvez pas modifier votre propre rôle."


class InvalidRole(ValidationFailed):
    default_code = "invalid_role"
    default_detail = "Rôle invalide."


class NotAReseller(BusinessRuleViolation):
    default_code = "not_a_reseller"
    default_detail = "Seuls les revendeurs ont une disponibilité."
