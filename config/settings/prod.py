from config.settings.base import *
from core.observability.logging import logging_config

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
# internal hosts: the Next server calls the api container directly; loopback: the health check
ALLOWED_HOSTS = [
    *env.list("DJANGO_ALLOWED_HOSTS"),
    *env.list("DJANGO_INTERNAL_HOSTS", default=["api"]),
    "localhost",
    "127.0.0.1",
]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^health/"]
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# only false for the local stack served over plain http
COOKIE_SECURE = env.bool("COOKIE_SECURE", default=True)
SESSION_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_SAMESITE = env.str("COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
SESSION_COOKIE_DOMAIN = env.str("SESSION_COOKIE_DOMAIN", default=None)
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_DOMAIN = env.str("CSRF_COOKIE_DOMAIN", default=None)

REST_AUTH["JWT_AUTH_SECURE"] = COOKIE_SECURE

SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = ["rest_framework.permissions.IsAdminUser"]
SPECTACULAR_SETTINGS["SERVE_AUTHENTICATION"] = [
    "rest_framework.authentication.SessionAuthentication",
    "dj_rest_auth.jwt_auth.JWTCookieAuthentication",
]

LOGGING = logging_config(json_logs=env.bool("LOG_JSON", default=True), level=LOG_LEVEL)

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

CORE = {**CORE, "HEALTH_CHECKS": ("database", "cache", "broker")}
