from collections.abc import Collection

from apps.content.models import Banner


class ContentMediaReferences:
    def referenced(self, urls: Collection[str]) -> set[str]:
        return set(Banner.objects.filter(image__in=list(urls)).values_list("image", flat=True))
