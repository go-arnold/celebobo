from django.apps import AppConfig


class LoyaltyConfig(AppConfig):
    name = "apps.loyalty"
    label = "loyalty"
    verbose_name = "Fidélité"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.loyalty.providers import register
        from core.container import container

        register(container)
