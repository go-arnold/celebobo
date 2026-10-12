from django.db import transaction

from apps.loyalty.domain.events import LoyaltySettingsChanged
from apps.loyalty.domain.settings import LoyaltySettingsChanges, Programmes
from apps.loyalty.selectors import to_programmes
from apps.loyalty.services.settings import LoyaltySettingsService
from core.domain.actor import Actor
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class LoyaltyFacade:
    def __init__(self, *, settings: LoyaltySettingsService, publisher: EventPublisher) -> None:
        self._settings = settings
        self._publisher = publisher

    def programmes(self) -> Programmes:
        return to_programmes(self._settings.current())

    def update(self, actor: Actor, changes: LoyaltySettingsChanges) -> Programmes:
        with transaction.atomic():
            if self._settings.update(changes):
                self._publisher.publish(LoyaltySettingsChanged(actor_id=actor.user_id))
        return self.programmes()
