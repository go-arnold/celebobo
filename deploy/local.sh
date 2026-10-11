#!/usr/bin/env bash
# Local stack, same containers and nginx routing as production: http://localhost:${NGINX_PORT:-8080}
#   ./deploy/local.sh up           build and start (api, worker, beat, nginx, postgres, redis, mailpit)
#   ./deploy/local.sh seed         fill the empty database with the demo catalogue and accounts
#   ./deploy/local.sh logs [svc]   follow logs        ./deploy/local.sh ps    status
#   ./deploy/local.sh manage ...   any manage.py command (createsuperuser, shell, ...)
#   ./deploy/local.sh down         stop               ./deploy/local.sh reset stop and delete all local data
#   anything else is passed to docker compose (e.g. ./deploy/local.sh --profile frontend up -d)
set -euo pipefail
cd "$(dirname "$0")"

export ENV_FILE=.env.local
[ -f "$ENV_FILE" ] || { cp .env.local.example "$ENV_FILE"; echo "Created deploy/$ENV_FILE from the example."; }
compose() { docker compose -p celebobo-local --env-file "$ENV_FILE" -f compose.yml -f compose.local.yml "$@"; }

case "${1:-up}" in
    up) shift; compose up -d --build --remove-orphans "$@"
        echo "API and site: http://localhost:${NGINX_PORT:-8080}   mail: http://localhost:${MAILPIT_PORT:-8025}" ;;
    seed) shift; compose run --rm api manage seed_demo --admin-email "${SEED_ADMIN_EMAIL:-admin@celebobo.test}" --no-images "$@" ;;
    logs) shift; compose logs -f --tail=100 "$@" ;;
    ps) compose ps ;;
    manage) shift; compose run --rm api manage "$@" ;;
    down) compose down ;;
    reset) compose down -v ;;
    *) compose "$@" ;;
esac
