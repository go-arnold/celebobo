#!/usr/bin/env bash
set -euo pipefail

role="${1:-api}"
shift || true

case "$role" in
    api)
        exec gunicorn config.asgi:application \
            --worker-class uvicorn_worker.UvicornWorker \
            --bind "0.0.0.0:${PORT:-8000}" \
            --workers="${WEB_CONCURRENCY:-2}" \
            --timeout="${GUNICORN_TIMEOUT:-120}" \
            --graceful-timeout=30 \
            --keep-alive=5 \
            --max-requests="${GUNICORN_MAX_REQUESTS:-2000}" \
            --max-requests-jitter=200 \
            --forwarded-allow-ips="*" \
            --access-logfile - \
            --error-logfile - \
            "$@"
        ;;
    worker)
        exec celery -A config worker \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --queues="${CELERY_QUEUES:-default}" \
            --concurrency="${CELERY_CONCURRENCY:-2}" \
            --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-500}" \
            --without-gossip --without-mingle \
            "$@"
        ;;
    beat)
        exec celery -A config beat \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --schedule=/tmp/celerybeat-schedule \
            "$@"
        ;;
    migrate)
        python manage.py migrate --noinput
        exec python manage.py check --deploy --fail-level ERROR
        ;;
    manage)
        exec python manage.py "$@"
        ;;
    *)
        exec "$role" "$@"
        ;;
esac
