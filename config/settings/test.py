from config.settings.base import *
from core.observability.logging import configure_structlog, logging_config

SECRET_KEY = "test-secret-key-for-celebobo-api-suite-0001"
DEBUG = False

# 127.0.0.1, not localhost: on Windows localhost can resolve to ::1, which Docker Desktop accepts
# and never answers. connect_timeout turns an unreachable database into an error instead of a hang.
DATABASES = {
    "default": env.db(
        "TEST_DATABASE_URL", default="postgres://celebobo:celebobo@127.0.0.1:5432/celebobo"
    ),
}
DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 5

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "celebobo-tests",
    },
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FRONTEND_URL = "https://app.test"
E2E_SEED_ALLOWED = True

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
WEBSOCKET_ALLOWED_ORIGINS = ["https://app.test"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"

MEDIA = {
    "CLOUD_NAME": "demo",
    "API_KEY": "123456789",
    "API_SECRET": "test-cloudinary-secret",
    "ROOT_FOLDER": "celebobo-test",
}

CORE = {
    **CORE,
    "EVENTS_DISPATCHER": "inline",
    "METRICS_BACKEND": "null",
    "PROBLEM_BASE_URI": "https://api.test/problems",
}

LOGGING = logging_config(json_logs=False, level="WARNING")
configure_structlog(cache_loggers=False)

STORAGES = {
    **STORAGES,
    "documents": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
}

ASSISTANT = {"PROVIDER": "offline", "DAILY_MESSAGES": 50}

MIDDLEWARE = [name for name in MIDDLEWARE if not name.startswith("whitenoise.")]
