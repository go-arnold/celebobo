from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

from core.domain.actor import Role

if TYPE_CHECKING:
    from apps.accounts.models import User


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **fields: Any) -> "User":
        if not email:
            raise ValueError("Users must have an email address")
        user = self.model(email=self.normalize_email(email).lower(), **fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **fields: Any) -> "User":
        from allauth.account.models import EmailAddress

        fields.update(is_staff=True, is_superuser=True, role=Role.ADMIN.value)
        user = self.create_user(email, password, **fields)
        # created from the command line: the address is trusted, so the site login works at once
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={"verified": True, "primary": True}
        )
        return user
