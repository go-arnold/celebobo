import secrets

from apps.accounts.domain.errors import ReferralCodesExhausted, UnknownReferralCode
from apps.accounts.models import User
from apps.accounts.services.contracts import CodeGenerator, UserStore

CODE_SPACE_START = 1000
CODE_SPACE_SIZE = 9000


def random_referral_code() -> str:
    return str(CODE_SPACE_START + secrets.randbelow(CODE_SPACE_SIZE))


class ReferralService:
    def __init__(
        self,
        users: UserStore,
        *,
        generate: CodeGenerator = random_referral_code,
        attempts: int = 25,
    ) -> None:
        self._users = users
        self._generate = generate
        self._attempts = attempts

    def resolve(self, code: str) -> User:
        reseller = self._users.active_reseller_by_code(code.strip())
        if reseller is None:
            raise UnknownReferralCode
        return reseller

    def issue_code(self) -> str:
        for _ in range(self._attempts):
            code = self._generate()
            if not self._users.referral_code_taken(code):
                return code
        raise ReferralCodesExhausted
