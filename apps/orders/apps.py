from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = "apps.orders"
    label = "orders"
    verbose_name = "Commandes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.orders.providers import register
        from core.container import container

        register(container)
