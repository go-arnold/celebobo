from django.apps import AppConfig


class CagnotteConfig(AppConfig):
    name = "apps.cagnotte"
    label = "cagnotte"
    verbose_name = "Cagnotte"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.cagnotte.providers import register
        from core.container import container

        register(container)
