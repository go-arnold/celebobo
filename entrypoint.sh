#!/usr/bin/env bash
set -euo pipefail

echo "Starting Celebobo API..."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

celery -A config worker \
    --loglevel=info \
    --concurrency="${CELERY_CONCURRENCY:-1}" \
    --queues=default,ai,exports &

celery -A config beat \
    --loglevel=info \
    --schedule=/tmp/celerybeat-schedule &

exec gunicorn config.asgi:application \
    --worker-class uvicorn_worker.UvicornWorker \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers="${WEB_CONCURRENCY:-1}" \
    --timeout=300 \
    --graceful-timeout=30 \
    --forwarded-allow-ips="*" \
    --access-logfile - \
    --error-logfile -
