#!/usr/bin/env bash
set -euo pipefail

# PROCESS_TYPE selects what this container runs:
#   all    (default) web + Celery worker + beat in one container; exits if any of them dies
#   web    ASGI only: REST, WebSockets and the assistant stream
#   rest   WSGI only (threaded): REST without WebSockets, behind a separate `web` service
#   worker Celery worker
#   beat   Celery beat (exactly one instance)
process="${PROCESS_TYPE:-all}"

migrate() {
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
        python manage.py migrate --noinput
    fi
}

web() {
    gunicorn config.asgi:application \
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
        --error-logfile -
}

rest() {
    gunicorn config.wsgi:application \
        --worker-class gthread \
        --bind "0.0.0.0:${PORT:-8000}" \
        --workers="${WEB_CONCURRENCY:-3}" \
        --threads="${WEB_THREADS:-4}" \
        --timeout="${WEB_TIMEOUT:-30}" \
        --graceful-timeout=20 \
        --keep-alive=5 \
        --max-requests="${WEB_MAX_REQUESTS:-1000}" \
        --max-requests-jitter=100 \
        --forwarded-allow-ips="*" \
        --access-logfile - \
        --error-logfile -
}

worker() {
    celery -A config worker \
        --loglevel=info \
        --queues="${CELERY_QUEUES:-default,ai,exports}" \
        --concurrency="${CELERY_CONCURRENCY:-1}" \
        --max-tasks-per-child=200 \
        -O fair \
        --without-gossip --without-mingle
}

beat() {
    celery -A config beat --loglevel=info --schedule=/tmp/celerybeat-schedule
}

echo "Starting Celebobo (${process})..."

case "$process" in
    all)
        migrate
        trap 'kill -TERM $(jobs -p) 2>/dev/null; wait' TERM INT
        worker &
        beat &
        web &
        wait -n
        echo "A Celebobo process stopped: exiting so the platform restarts the container." >&2
        exit 1
        ;;
    web) migrate; web ;;
    rest) rest ;;
    worker) worker ;;
    beat) beat ;;
    *) echo "Unknown PROCESS_TYPE: ${process}" >&2; exit 64 ;;
esac
