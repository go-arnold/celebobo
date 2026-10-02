from itertools import cycle

import pytest

from apps.accounts.domain.commands import RegisterUser, UpdatePreferences
from apps.accounts.domain.enums import NotificationChannel, NotificationTopic
from apps.accounts.domain.errors import (
    EmailAlreadyUsed,
    PhoneAlreadyUsed,
    ReferralCodesExhausted,
    UnknownReferralCode,
)
from apps.accounts.domain.normalization import clean_text, normalize_email, normalize_phone
from apps.accounts.models import User
from apps.accounts.services.preferences import PreferenceService
from apps.accounts.services.referrals import ReferralService, random_referral_code
from apps.accounts.services.registration import RegistrationService
from apps.accounts.services.tickets import TicketService
from apps.accounts.tests.fakes import (
    AcceptAllPasswords,
    InMemoryPreferences,
    InMemoryTickets,
    InMemoryUsers,
)
from core.domain.actor import Role


def reseller(pk: int = 10, code: str = "4821", *, active: bool = True) -> User:
    return User(
        pk=pk,
        email=f"reseller{pk}@celebobo.test",
        role=Role.RESELLER.value,
        referral_code=code,
        is_active=active,
    )


def command(**overrides) -> RegisterUser:
    values = {
        "first_name": "  Aline ",
        "last_name": "Mbuyi",
        "email": " Aline@Celebobo.TEST ",
        "password": "Kinshasa-2026!",
    }
    return RegisterUser(**{**values, **overrides})


class TestNormalization:
    def test_email(self):
        assert normalize_email("  Aline@Celebobo.TEST ") == "aline@celebobo.test"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(None, None), ("   ", None), ("+243  81 234   567", "+243 81 234 567")],
    )
    def test_phone(self, raw, expected):
        assert normalize_phone(raw) == expected

    def test_text(self):
        assert clean_text("  Jean   Pierre ") == "Jean Pierre"


class TestReferralService:
    def test_resolves_active_reseller(self):
        service = ReferralService(InMemoryUsers([reseller()]))

        assert service.resolve(" 4821 ").pk == 10

    @pytest.mark.parametrize("users", [[], [reseller(active=False)]])
    def test_unknown_or_inactive_codes_are_rejected(self, users):
        with pytest.raises(UnknownReferralCode):
            ReferralService(InMemoryUsers(users)).resolve("4821")

    def test_issue_skips_taken_codes(self):
        codes = iter(["4821", "4821", "5000"])
        service = ReferralService(InMemoryUsers([reseller()]), generate=lambda: next(codes))

        assert service.issue_code() == "5000"

    def test_issue_gives_up_after_attempts(self):
        codes = cycle(["4821"])
        service = ReferralService(
            InMemoryUsers([reseller()]), generate=lambda: next(codes), attempts=3
        )

        with pytest.raises(ReferralCodesExhausted):
            service.issue_code()

    def test_random_codes_are_four_digits(self):
        assert all(len(random_referral_code()) == 4 for _ in range(200))
        assert all(random_referral_code().isdigit() for _ in range(200))


class TestRegistrationService:
    def service(self, users: InMemoryUsers) -> RegistrationService:
        return RegistrationService(users, ReferralService(users), AcceptAllPasswords())

    def test_normalizes_and_creates_a_client(self):
        users = InMemoryUsers()

        user = self.service(users).register(command(phone_number=" +243 81 000 0000 "))

        assert user.email == "aline@celebobo.test"
        assert user.first_name == "Aline"
        assert user.phone_number == "+243 81 000 0000"
        assert user.role == Role.CLIENT.value
        assert user.check_password("Kinshasa-2026!")

    def test_attaches_inviter(self):
        users = InMemoryUsers([reseller()])

        user = self.service(users).register(command(referral_code="4821"))

        assert user.invited_by is not None
        assert user.invited_by.pk == 10

    def test_rejects_duplicate_email_case_insensitively(self):
        users = InMemoryUsers([User(pk=1, email="aline@celebobo.test")])

        with pytest.raises(EmailAlreadyUsed) as error:
            self.service(users).register(command())
        assert "email" in error.value.errors

    def test_rejects_duplicate_phone(self):
        users = InMemoryUsers([User(pk=1, email="x@celebobo.test", phone_number="+243 81")])

        with pytest.raises(PhoneAlreadyUsed):
            self.service(users).register(command(email="new@celebobo.test", phone_number="+243 81"))


class TestPreferenceService:
    def test_defaults(self):
        preferences = PreferenceService(InMemoryPreferences()).current(1)

        assert preferences["promotions"] == {"email": True, "push": False}
        assert preferences["new_message"] == {"email": True, "push": True}

    def test_partial_update_merges_with_defaults(self):
        store = InMemoryPreferences()
        service = PreferenceService(store)

        service.update(
            1,
            UpdatePreferences(
                preferences={NotificationTopic.NEW_MESSAGE: {NotificationChannel.PUSH: False}}
            ),
        )

        assert service.current(1)["new_message"] == {"email": True, "push": False}
        assert service.current(1)["order_assigned"] == {"email": True, "push": True}

    def test_unknown_stored_keys_are_ignored(self):
        store = InMemoryPreferences()
        store.store(1, {"legacy_topic": {"sms": True}})

        assert "legacy_topic" not in PreferenceService(store).current(1)


class TestTicketService:
    def test_ticket_is_single_use(self):
        service = TicketService(InMemoryTickets(), ttl=30)

        ticket = service.issue(7)

        assert ticket.expires_in == 30
        assert service.redeem(ticket.ticket) == 7
        assert service.redeem(ticket.ticket) is None

    def test_empty_ticket(self):
        assert TicketService(InMemoryTickets()).redeem("") is None
