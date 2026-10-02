import json

import structlog
from pywebpush import WebPushException, webpush

from apps.push.conf import PushSettings
from apps.push.domain.messages import DeliveryOutcome, Endpoint, PushMessage

GONE_STATUSES = frozenset({404, 410})
TIMEOUT_SECONDS = 10

logger = structlog.get_logger(__name__)


class WebPushSender:
    def __init__(self, settings: PushSettings) -> None:
        self._settings = settings

    def send(self, endpoint: Endpoint, message: PushMessage) -> DeliveryOutcome:
        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint.url,
                    "keys": {"p256dh": endpoint.p256dh, "auth": endpoint.auth},
                },
                data=json.dumps(message.payload(), ensure_ascii=False),
                vapid_private_key=self._settings.vapid_private_key,
                vapid_claims={"sub": self._settings.vapid_subject},
                ttl=self._settings.ttl,
                timeout=TIMEOUT_SECONDS,
            )
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in GONE_STATUSES:
                return DeliveryOutcome.GONE
            logger.warning("push.delivery_failed", status=status)
            return DeliveryOutcome.FAILED
        return DeliveryOutcome.DELIVERED
