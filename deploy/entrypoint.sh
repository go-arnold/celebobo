#!/usr/bin/env bash
set -euo pipefail

# One image, one role per container: api | worker | beat | migrate | manage <command> | <any executable>
role="${1:-api}"
shift || true

case "$role" in
    api)
        # Uvicorn workers on ASGI: REST, the assistant stream (SSE) and WebSockets.
        # Each worker serves one synchronous request at a time: WEB_CONCURRENCY is the parallelism (~140 MB each).
        exec gunicorn config.asgi:application \
            --worker-class uvicorn_worker.UvicornWorker \
            --bind "0.0.0.0:${PORT:-8000}" \
            --workers="${WEB_CONCURRENCY:-3}" \
            --timeout="${WEB_TIMEOUT:-30}" \
            --graceful-timeout=20 \
            --keep-alive=5 \
            --max-requests="${WEB_MAX_REQUESTS:-1000}" \
            --max-requests-jitter=100 \
            --forwarded-allow-ips="*" \
            --access-logfile - \
            --error-logfile - \
            "$@"
        ;;
    worker)
        exec celery -A config worker \
            --loglevel="${CELERY_LOG_LEVEL:-info}" \
            --queues="${CELERY_QUEUES:-default,ai,exports}" \
            --concurrency="${CELERY_CONCURRENCY:-2}" \
            --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-200}" \
            -O fair \
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
