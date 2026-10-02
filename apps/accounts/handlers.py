from apps.accounts.domain.events import PasswordResetRequested, UserCreated, UserRegistered
from apps.accounts.services.contracts import EmailVerifier
from apps.accounts.services.mailer import AccountMailer
from core.container import container
from core.events.bus import event_bus


@event_bus.on(UserRegistered, background=True)
def send_verification_email(event: UserRegistered) -> None:
    if not event.via_social:
        container.resolve(EmailVerifier).send_verification(event.user_id)


@event_bus.on(UserCreated, background=True)
def invite_created_user(event: UserCreated) -> None:
    container.resolve(AccountMailer).account_created(event.user_id)


@event_bus.on(PasswordResetRequested, background=True)
def send_staff_password_reset(event: PasswordResetRequested) -> None:
    container.resolve(AccountMailer).password_reset(event.user_id)
