from collections.abc import Collection

from apps.accounts.models import User


class AccountMediaReferences:
    def referenced(self, urls: Collection[str]) -> set[str]:
        return set(User.objects.filter(avatar__in=list(urls)).values_list("avatar", flat=True))
