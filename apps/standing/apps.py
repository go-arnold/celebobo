from django.apps import AppConfig


class StandingConfig(AppConfig):
    name = "apps.standing"
    label = "standing"
    verbose_name = "Niveaux et sanctions des revendeurs"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.standing.providers import register
        from core.container import container

        register(container)
