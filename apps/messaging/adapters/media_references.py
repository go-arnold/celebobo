from collections.abc import Collection

from apps.messaging.models import Message


class MessagingMediaReferences:
    def referenced(self, urls: Collection[str]) -> set[str]:
        return set(
            Message.objects.filter(attachment__in=list(urls)).values_list("attachment", flat=True)
        )
