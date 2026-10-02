from datetime import timedelta
from pathlib import Path

import django_stubs_ext
import environ

from core.observability.logging import configure_structlog, logging_config

django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
if (BASE_DIR / ".env").is_file():
    environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="django-insecure-local-only")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "safedelete",
    "core",
    "apps.accounts",
    "apps.catalog",
    "apps.orders",
    "apps.messaging",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "core.observability.middleware.request_context_middleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db(
        "DATABASE_URL", default="postgres://celebobo:celebobo@localhost:5432/celebobo"
    ),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=0)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = env.bool("DATABASE_POOLER", default=False)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env.str("REDIS_CACHE_URL", default="redis://localhost:6379/0"),
        "KEY_PREFIX": "celebobo",
        "TIMEOUT": 300,
    },
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
TIME_ZONE = env.str("TIME_ZONE", default="Africa/Kinshasa")
USE_I18N = True
USE_TZ = True

FORMS_URLFIELD_ASSUME_HTTPS = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

REST_FRAMEWORK = {
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
    "VERSION_PARAM": "version",
    "DEFAULT_AUTHENTICATION_CLASSES": ("dj_rest_auth.jwt_auth.JWTCookieAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.api.pagination.PagePagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.api.exceptions.problem_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "240/min",
        "auth": "10/min",
        "dj_rest_auth": "10/min",
        "referral": "20/min",
        "search": "120/min",
        "tracking": "10/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Celebobo API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

CORS_ALLOWED_ORIGINS: list[str] = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    "accept",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-cart-token",
    "x-csrftoken",
    "x-request-id",
)
CORS_EXPOSE_HEADERS = ("x-request-id", "idempotent-replayed", "retry-after")
CSRF_TRUSTED_ORIGINS: list[str] = env.list("CSRF_TRUSTED_ORIGINS", default=[])

FRONTEND_URL = env.str("FRONTEND_URL", default="http://localhost:3000")
GOOGLE_OAUTH_CALLBACK_URL = env.str("GOOGLE_OAUTH_CALLBACK_URL", default=FRONTEND_URL)

ACCOUNT_ADAPTER = "apps.accounts.adapters.allauth.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.allauth.SocialAccountAdapter"
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = env.str("ACCOUNT_EMAIL_VERIFICATION", default="mandatory")
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_CONFIRM_EMAIL_ON_GET = False
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": env.str("GOOGLE_CLIENT_ID", default=""),
                "secret": env.str("GOOGLE_CLIENT_SECRET", default=""),
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "EMAIL_AUTHENTICATION": True,
    },
}

REST_AUTH = {
    "USE_JWT": True,
    "TOKEN_MODEL": None,
    "SESSION_LOGIN": False,
    "JWT_AUTH_COOKIE": "cb_access",
    "JWT_AUTH_REFRESH_COOKIE": "cb_refresh",
    "JWT_AUTH_REFRESH_COOKIE_PATH": "/api/",
    "JWT_AUTH_HTTPONLY": True,
    "JWT_AUTH_SAMESITE": "Lax",
    "JWT_AUTH_SECURE": env.bool("JWT_AUTH_SECURE", default=False),
    "JWT_AUTH_COOKIE_DOMAIN": env.str("JWT_AUTH_COOKIE_DOMAIN", default=None),
    "JWT_AUTH_COOKIE_USE_CSRF": True,
    "JWT_AUTH_RETURN_EXPIRATION": True,
    "LOGOUT_ON_PASSWORD_CHANGE": False,
    "OLD_PASSWORD_FIELD_ENABLED": True,
    "USER_DETAILS_SERIALIZER": "apps.accounts.api.v1.auth_serializers.SessionUserSerializer",
    "PASSWORD_RESET_SERIALIZER": (
        "apps.accounts.api.v1.auth_serializers.FrontendPasswordResetSerializer"
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="Celebobo <no-reply@celebobo.com>")

CATALOG = {
    "SEARCH_ENGINE": env.str("CATALOG_SEARCH_ENGINE", default="database"),
    "SEARCH_INDEX": env.str("CATALOG_SEARCH_INDEX", default="null"),
    "NEW_PRODUCT_DAYS": env.int("CATALOG_NEW_PRODUCT_DAYS", default=20),
    "CACHE_TTL": env.int("CATALOG_CACHE_TTL", default=300),
}
ORDERS = {
    "FREE_SHIPPING_THRESHOLD": env.str("ORDERS_FREE_SHIPPING_THRESHOLD", default="199.00"),
    "FLAT_SHIPPING_FEE": env.str("ORDERS_FLAT_SHIPPING_FEE", default="2.98"),
}
MEILISEARCH = {
    "URL": env.str("MEILISEARCH_URL", default="http://localhost:7700"),
    "API_KEY": env.str("MEILISEARCH_API_KEY", default=""),
    "INDEX": env.str("MEILISEARCH_INDEX", default="products"),
}

CELERY_BROKER_URL = env.str("REDIS_BROKER_URL", default="redis://localhost:6379/1")
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE

CORE = {
    "EVENTS_DISPATCHER": env.str("CORE_EVENTS_DISPATCHER", default="celery"),
    "METRICS_BACKEND": env.str("CORE_METRICS_BACKEND", default="log"),
    "PROBLEM_BASE_URI": env.str(
        "CORE_PROBLEM_BASE_URI", default="https://api.celebobo.com/problems"
    ),
    "HEALTH_CHECKS": ("database", "cache"),
}

LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")
LOG_JSON = env.bool("LOG_JSON", default=False)
LOGGING = logging_config(json_logs=LOG_JSON, level=LOG_LEVEL)
configure_structlog()
