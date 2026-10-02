from collections.abc import Iterable, Iterator, Mapping
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory
from apps.realtime.domain.protocol import ServerEvent
from apps.realtime.services.contracts import Broadcaster
from apps.realtime.services.presence import PresenceService
from core.container import container

pytestmark = pytest.mark.django_db(transaction=True)


class RecordingBroadcaster:
    def __init__(self) -> None:
        self.sent: list[tuple[tuple[str, ...], ServerEvent, dict[str, Any]]] = []

    def send(self, groups: Iterable[str], event: ServerEvent, data: Mapping[str, Any]) -> None:
        self.sent.append((tuple(groups), event, dict(data)))


@pytest.fixture
def broadcaster() -> Iterator[RecordingBroadcaster]:
    recording = RecordingBroadcaster()
    with container.override(Broadcaster, recording):
        yield recording


def authenticated(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


class TestPresenceApi:
    def test_managers_see_who_is_online(self):
        online, offline = ResellerFactory.create(), ResellerFactory.create()
        container.resolve(PresenceService).connected(online.pk)

        response = authenticated(ManagerFactory.create()).get(
            f"/api/v1/bo/presence/?ids={online.pk}&ids={offline.pk}"
        )

        assert response.json() == {"online": [online.pk]}

    def test_resellers_cannot_query_presence(self):
        reseller = ResellerFactory.create()

        response = authenticated(reseller).get(f"/api/v1/bo/presence/?ids={reseller.pk}")

        assert response.status_code == 403

    def test_ids_are_required(self):
        response = authenticated(ManagerFactory.create()).get("/api/v1/bo/presence/")

        assert response.status_code == 400


class TestAvailabilityRelay:
    def test_manual_availability_is_pushed_to_staff(self, broadcaster):
        reseller = ResellerFactory.create()

        authenticated(reseller).patch("/api/v1/bo/me/availability/", {"availability": "away"})

        groups, event, data = broadcaster.sent[-1]
        assert groups == ("staff",)
        assert event is ServerEvent.PRESENCE_CHANGED
        assert data == {"user_id": reseller.pk, "online": True, "availability": "away"}
