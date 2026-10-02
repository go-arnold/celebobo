from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "Analytique"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.analytics.providers import register
        from core.container import container

        register(container)
