from collections.abc import Mapping
from types import MappingProxyType

from apps.accounts.domain.enums import NotificationChannel, NotificationTopic

DEFAULT_PREFERENCES: Mapping[NotificationTopic, Mapping[NotificationChannel, bool]] = (
    MappingProxyType(
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
)
