from django.apps import AppConfig


class CashConfig(AppConfig):
    name = "apps.cash"
    label = "cash"
    verbose_name = "Encaissements des revendeurs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.cash.providers import register
        from core.container import container

        register(container)
