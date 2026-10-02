from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "apps.audit"
    label = "audit"
    verbose_name = "Journal d'audit"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.audit import receivers
        from apps.audit.providers import register
        from core.container import container

        register(container)
        receivers.connect()
