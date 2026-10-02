from collections.abc import Iterable

from django.db import transaction

from apps.push.domain.messages import DeviceView, PushMessage, RegisterDevice, SendResult
from apps.push.selectors import DeviceSelector, to_device_view
from apps.push.services.devices import DeviceService, PushDispatcher
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.observability.decorators import logged_facade

NOTHING_SENT = SendResult(delivered=0, removed=0, failed=0)


@logged_facade
class PushFacade:
    def __init__(
        self,
        *,
        devices: DeviceService,
        dispatcher: PushDispatcher,
        selector: DeviceSelector,
        public_key: str,
        enabled: bool,
    ) -> None:
        self._devices = devices
        self._dispatcher = dispatcher
        self._selector = selector
        self._public_key = public_key
        self._enabled = enabled

    def public_key(self) -> tuple[str, bool]:
        return self._public_key, self._enabled

    def devices(self, actor: Actor) -> list[DeviceView]:
        return self._selector.for_user(_user_id(actor))

    def register(self, actor: Actor, command: RegisterDevice) -> DeviceView:
        with transaction.atomic():
            return to_device_view(self._devices.register(_user_id(actor), command))

    def remove(self, actor: Actor, device_id: int) -> None:
        with transaction.atomic():
            self._devices.remove(_user_id(actor), device_id)

    def send(self, user_ids: Iterable[int], message: PushMessage) -> SendResult:
        if not self._enabled:
            return NOTHING_SENT
        with transaction.atomic():
            return self._dispatcher.send(user_ids, message)


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id
