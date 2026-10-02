from config.settings.base import *
from core.observability.logging import configure_structlog, logging_config

SECRET_KEY = "test-secret-key-for-celebobo-api-suite-0001"
DEBUG = False

DATABASES = {
    "default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:"),
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "celebobo-tests",
    },
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FRONTEND_URL = "https://app.test"

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
WEBSOCKET_ALLOWED_ORIGINS = ["https://app.test"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

CORE = {
    **CORE,
    "EVENTS_DISPATCHER": "inline",
    "METRICS_BACKEND": "null",
    "PROBLEM_BASE_URI": "https://api.test/problems",
}

LOGGING = logging_config(json_logs=False, level="WARNING")
configure_structlog(cache_loggers=False)
