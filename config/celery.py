import os

from celery import Celery

from core.observability.celery import install_context_propagation

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("celebobo")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
install_context_propagation()
