from apps.push.domain.messages import DeviceView
from apps.push.models import PushSubscription


class DeviceSelector:
    def for_user(self, user_id: int) -> list[DeviceView]:
        return [to_device_view(item) for item in PushSubscription.objects.filter(user_id=user_id)]


def to_device_view(subscription: PushSubscription) -> DeviceView:
    return DeviceView(
        id=subscription.pk,
        user_agent=subscription.user_agent,
        created_at=subscription.created_at,
        last_used_at=subscription.last_used_at,
    )
