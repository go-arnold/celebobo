#!/usr/bin/env bash
# Production on a VPS (Docker + Compose): nginx with Let's Encrypt in front of the containers;
# Postgres (Supabase) and Redis (Aiven) stay hosted. See deploy/README.md.
#   ./deploy/prod.sh certs         first time only: obtain the TLS certificate (ports 80/443 free)
#   ./deploy/prod.sh up            build and (re)start everything, with zero manual steps
#   ./deploy/prod.sh logs [svc]    ./deploy/prod.sh ps    ./deploy/prod.sh manage <command>
#   anything else is passed to docker compose
set -euo pipefail
cd "$(dirname "$0")"

export ENV_FILE=.env.prod
[ -f "$ENV_FILE" ] || { echo "Missing deploy/$ENV_FILE: copy .env.prod.example and fill it in." >&2; exit 1; }
compose() { docker compose -p celebobo --env-file "$ENV_FILE" -f compose.yml -f compose.prod.yml "$@"; }
setting() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }

case "${1:-up}" in
    certs)
        domains=(-d "$(setting DOMAIN)")
        for extra in $(setting EXTRA_DOMAINS); do domains+=(-d "$extra"); done
        compose run --rm -p 80:80 --entrypoint certbot certbot certonly --standalone --non-interactive \
            --agree-tos --email "$(setting LETSENCRYPT_EMAIL)" "${domains[@]}" ;;
    up) shift; compose up -d --build --remove-orphans "$@" ;;
    logs) shift; compose logs -f --tail=200 "$@" ;;
    ps) compose ps ;;
    manage) shift; compose run --rm api manage "$@" ;;
    *) compose "$@" ;;
esac
