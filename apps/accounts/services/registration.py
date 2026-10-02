from apps.accounts.domain.commands import RegisterUser
from apps.accounts.domain.errors import EmailAlreadyUsed, PhoneAlreadyUsed
from apps.accounts.domain.normalization import clean_text, normalize_email, normalize_phone
from apps.accounts.models import User
from apps.accounts.services.contracts import PasswordPolicy, UserStore
from apps.accounts.services.referrals import ReferralService
from core.domain.actor import Role


class RegistrationService:
    def __init__(
        self, users: UserStore, referrals: ReferralService, passwords: PasswordPolicy
    ) -> None:
        self._users = users
        self._referrals = referrals
        self._passwords = passwords

    def register(self, command: RegisterUser) -> User:
        email = normalize_email(command.email)
        phone = normalize_phone(command.phone_number)
        if self._users.email_taken(email):
            raise EmailAlreadyUsed
        if phone and self._users.phone_taken(phone):
            raise PhoneAlreadyUsed
        inviter = self._referrals.resolve(command.referral_code) if command.referral_code else None
        first_name, last_name = clean_text(command.first_name), clean_text(command.last_name)
        self._passwords.validate(
            command.password, user=User(email=email, first_name=first_name, last_name=last_name)
        )
        return self._users.create(
            email=email,
            password=command.password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone,
            invited_by=inviter,
            role=Role.CLIENT.value,
        )
