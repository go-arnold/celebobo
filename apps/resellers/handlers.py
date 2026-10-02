from apps.resellers.domain.events import (
    ApplicationApproved,
    ApplicationRejected,
    ApplicationSubmitted,
)
from apps.resellers.selectors import ApplicationSelector
from apps.resellers.services.mailer import ApplicationMailer
from core.container import container
from core.events.bus import event_bus


def _mailer() -> ApplicationMailer:
    return container.resolve(ApplicationMailer)


@event_bus.on(ApplicationSubmitted, background=True)
def acknowledge_application(event: ApplicationSubmitted) -> None:
    _mailer().received(ApplicationSelector().one(event.application_id))


@event_bus.on(ApplicationApproved, background=True)
def welcome_reseller(event: ApplicationApproved) -> None:
    application = ApplicationSelector().one(event.application_id)
    _mailer().approved(application, account_created=event.account_created)


@event_bus.on(ApplicationRejected, background=True)
def announce_rejection(event: ApplicationRejected) -> None:
    _mailer().rejected(ApplicationSelector().one(event.application_id))
