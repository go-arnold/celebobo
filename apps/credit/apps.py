from django.apps import AppConfig


class CreditConfig(AppConfig):
    name = "apps.credit"
    label = "credit"
    verbose_name = "Avoirs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.credit.providers import register
        from core.container import container

        register(container)
