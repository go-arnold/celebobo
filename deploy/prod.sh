#!/usr/bin/env bash
# Production on a VPS (Docker + Compose): nginx with Let's Encrypt in front of the containers;
# Postgres and Redis on this server (COMPOSE_PROFILES=data) or hosted. See deploy/README.md.
#   ./deploy/prod.sh certs         first time only: obtain the TLS certificate (ports 80/443 free)
#   ./deploy/prod.sh up            build and (re)start everything, with zero manual steps
#   ./deploy/prod.sh logs [svc]    ./deploy/prod.sh ps    ./deploy/prod.sh manage <command>
#   ./deploy/prod.sh import-db     copy SOURCE_DATABASE_URL into the local Postgres (site stopped meanwhile)
#   ./deploy/prod.sh compare-db    row counts of every table, source against local
#   ./deploy/prod.sh backup        a database dump now, in deploy/backups
#   anything else is passed to docker compose
set -euo pipefail
cd "$(dirname "$0")"

export ENV_FILE=.env.prod
[ -f "$ENV_FILE" ] || { echo "Missing deploy/$ENV_FILE: copy .env.prod.example and fill it in." >&2; exit 1; }
compose() { docker compose -p celebobo --env-file "$ENV_FILE" -f compose.yml -f compose.prod.yml "$@"; }
setting() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
source_url() {
    local url
    url="$(setting SOURCE_DATABASE_URL)"
    [ -n "$url" ] || { echo "Set SOURCE_DATABASE_URL in deploy/$ENV_FILE (Supabase session pooler, port 5432)." >&2; exit 1; }
    echo "$url"
}
local_psql() { compose exec -T postgres psql -U celebobo -d celebobo -v ON_ERROR_STOP=1 "$@"; }
source_psql() { compose exec -T -e SOURCE_URL="$(source_url)" postgres sh -c 'psql "$SOURCE_URL" -v ON_ERROR_STOP=1 "$@"' psql "$@"; }

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
    import-db)
        source_url >/dev/null
        compose stop api worker beat
        compose up -d --wait postgres redis
        compose run --rm migrate
        local_psql < postgres/truncate.sql
        compose exec -T -e SOURCE_URL="$(source_url)" postgres sh -c '
            pg_dump "$SOURCE_URL" --data-only --schema=public --exclude-table-data=public.django_migrations \
                --format=custom --file=/tmp/import.dump \
            && pg_restore --data-only --disable-triggers --exit-on-error -U celebobo -d celebobo /tmp/import.dump \
            && rm /tmp/import.dump'
        local_psql -c "refresh materialized view analytics_sales_fact"
        echo "Imported. Check with ./deploy/prod.sh compare-db, then start with ./deploy/prod.sh up" ;;
    compare-db)
        diff <(source_psql -At < postgres/row-counts.sql) <(local_psql -At < postgres/row-counts.sql) \
            && echo "Same row count in every table." ;;
    backup) compose exec backup sh /usr/local/bin/backup.sh once ;;
    *) compose "$@" ;;
esac
