from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documents et exports"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.documents.providers import register
        from core.container import container

        register(container)
