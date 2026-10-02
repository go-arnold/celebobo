# Production deployment

A multi-container setup: one image, one role per container.

| Service | Role | Notes |
|---|---|---|
| `migrate` | `migrate` | Runs `migrate`, then `check --deploy`. Every other service waits for it to finish. |
| `api` | `api` | Gunicorn with Uvicorn workers on `config.asgi`. Serves REST, SSE and WebSockets. Healthcheck on `/health/live/`. |
| `worker-default` | `worker` | Queue `default`: notifications, emails, realtime fan-out, analytics refresh, audit. |
| `worker-ai` | `worker` | Queue `ai`: assistant embeddings, insights and summaries. |
| `worker-exports` | `worker` | Queue `exports`: CSV/XLSX/PDF jobs and imports. Shares the `documents` volume with `api`. |
| `beat` | `beat` | Celery beat: analytics refresh and the daily purges and sweeps. Run exactly one. |

Routing lives in `config/celery_routes.py`. Background domain-event handlers in `apps.assistant` go to `ai`, those in `apps.documents` go to `exports`, and everything else goes to `default`.

## Run

```bash
cp deploy-real-prod/.env.prod.example deploy-real-prod/.env.prod
docker compose -f deploy-real-prod/docker-compose.yml build
docker compose -f deploy-real-prod/docker-compose.yml up -d
docker compose -f deploy-real-prod/docker-compose.yml logs -f api
```

Without Supabase and Aiven, `--profile local-infra` adds Postgres 16 with pgvector, pgbouncer (transaction mode) and Redis. In that case, point the URLs at `pgbouncer:5432` and `redis:6379`.

The roles also run one-off commands:

```bash
docker compose -f deploy-real-prod/docker-compose.yml run --rm api manage createsuperuser
docker compose -f deploy-real-prod/docker-compose.yml run --rm api manage shell
```

## Checklist

- **Secrets and hosts:**
  - `DJANGO_SECRET_KEY` is a long random value;
  - `DJANGO_ALLOWED_HOSTS` is the API hostname;
  - `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and `WEBSOCKET_ALLOWED_ORIGINS` list the frontend origin.
- **Cookies:** `SESSION_COOKIE_DOMAIN`, `CSRF_COOKIE_DOMAIN` and `JWT_AUTH_COOKIE_DOMAIN` are the shared parent domain (`.celebobo.cd`) when the API and frontend use sibling subdomains.
- **Cookies across sites:** if the frontend and API are on different sites (for example `vercel.app` and `koyeb.app`), set `COOKIE_SAMESITE=None` and leave the cookie domains empty. Browsers that block third-party cookies (Safari by default) will still drop them, so production should use one domain: `celebobo.cd` and `api.celebobo.cd`.
- **Database:**
  - `DATABASE_URL` goes through a pooler with `DATABASE_POOLER=true`, which turns off server-side cursors and psycopg prepared statements;
  - the `vector` extension is enabled (the first assistant migration creates it).
- **Redis:** the URLs use `rediss://` for TLS. The broker URL also needs `?ssl_cert_reqs=required`.
- **Behind a proxy:** `AXES_PROXY_COUNT` matches the number of proxies in front of the API, so login lockouts target the real client IP.
- **Email:** `EMAIL_URL` points at a real SMTP relay (verification and password emails depend on it).
- **Integrations:**
  - `CLOUDINARY_*` for uploads;
  - `GEMINI_API_KEY` with `ASSISTANT_PROVIDER=gemini` for the assistant;
  - `VAPID_*` for browser push.
- **After the first deploy:**
  - `manage createsuperuser`;
  - `POST /api/v1/bo/embeddings/reindex/` once to embed the catalogue.
- **Healthchecks:** use the `/health/live/` endpoint; `/health/ready/` also checks the database, the cache and the broker. HTTPS redirect is disabled on `/health/` so probes get an answer.
- **Static files:** WhiteNoise serves them from the image (collected at build time).
- **Logs:** JSON lines on stdout (`LOG_JSON=true`). Ship them with the platform's log drain.
