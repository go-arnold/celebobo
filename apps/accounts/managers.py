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
        fields.update(is_staff=True, is_superuser=True, role=Role.ADMIN.value)
        return self.create_user(email, password, **fields)
