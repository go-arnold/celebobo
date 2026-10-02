from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from apps.accounts.domain.commands import UpdatePreferences
from apps.accounts.domain.enums import NotificationChannel, NotificationTopic
from apps.accounts.services.contracts import PreferenceStore

type Preferences = dict[str, dict[str, bool]]

DEFAULTS: Mapping[NotificationTopic, Mapping[NotificationChannel, bool]] = MappingProxyType(
    {
        NotificationTopic.ORDER_ASSIGNED: {
            NotificationChannel.EMAIL: True,
            NotificationChannel.PUSH: True,
        },
        NotificationTopic.STATUS_CHANGED: {
            NotificationChannel.EMAIL: True,
            NotificationChannel.PUSH: True,
        },
        NotificationTopic.NEW_MESSAGE: {
            NotificationChannel.EMAIL: True,
            NotificationChannel.PUSH: True,
        },
        NotificationTopic.PROMOTIONS: {
            NotificationChannel.EMAIL: True,
            NotificationChannel.PUSH: False,
        },
    }
)


class PreferenceService:
    def __init__(self, store: PreferenceStore) -> None:
        self._store = store

    def current(self, user_id: int) -> Preferences:
        return _merge(self._store.stored_for(user_id))

    def update(self, user_id: int, command: UpdatePreferences) -> Preferences:
        merged = self.current(user_id)
        for topic, channels in command.preferences.items():
            for channel, enabled in channels.items():
                merged[topic.value][channel.value] = bool(enabled)
        self._store.store(user_id, merged)
        return merged


def _merge(stored: Mapping[str, Any]) -> Preferences:
    merged: Preferences = {}
    for topic, channels in DEFAULTS.items():
        saved = stored.get(topic.value, {})
        merged[topic.value] = {
            channel.value: bool(saved.get(channel.value, default))
            for channel, default in channels.items()
        }
    return merged
