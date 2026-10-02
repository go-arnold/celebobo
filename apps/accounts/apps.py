from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Comptes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.accounts.providers import register
        from core.container import container

        register(container)
