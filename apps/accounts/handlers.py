from apps.accounts.domain.events import UserRegistered
from apps.accounts.services.contracts import EmailVerifier
from core.container import container
from core.events.bus import event_bus


@event_bus.on(UserRegistered, background=True)
def send_verification_email(event: UserRegistered) -> None:
    if not event.via_social:
        container.resolve(EmailVerifier).send_verification(event.user_id)
