# Deployment

One Docker image for Django, one for the Next.js frontend, nginx in front. The same files run in two places:

| | `./deploy/local.sh` (your machine) | `./deploy/prod.sh` (VPS) |
|---|---|---|
| Address | `http://localhost:8080` | `https://DOMAIN` |
| Postgres | container (pgvector, port 55432 on the host) | container on the server (profile `data`), or Supabase |
| Redis | container | container on the server (profile `data`), or Aiven |
| Email | Mailpit, inbox at `http://localhost:8025` | your SMTP relay |
| TLS | none | Let's Encrypt, renewed automatically |
| Frontend | `npm run dev` on the host (hot reload), or the container | container (or Vercel) |
| Django settings | `config.settings.prod` | `config.settings.prod` |

```
browser ──► nginx ──► /api/ /ws/ /django-admin/ /static/ /health/ ──► api (gunicorn + uvicorn: REST, SSE, WebSockets)
                 └──► everything else ─────────────────────────────► frontend (Next.js)
            worker (Celery: default, ai, exports) · beat (schedule) · migrate (runs once, before the others)
```

The site and the API share one origin: cookies stay first-party, no CORS, and the WebSocket uses the same host.

## Services

| Service | Image / command | Notes |
|---|---|---|
| `migrate` | api `migrate` | `migrate` then `check --deploy`; every app container waits for it |
| `api` | api `api` | `WEB_CONCURRENCY` workers (one request at a time each, ~140 MB each), 30 s timeout (`WEB_TIMEOUT`) |
| `worker` | api `worker` | queues `default,ai,exports` (`CELERY_QUEUES`), `CELERY_CONCURRENCY` processes |
| `beat` | api `beat` | periodic tasks; run exactly one |
| `frontend` | frontend | profile `frontend`; built from `FRONTEND_DIR` (default `../../shopproject_v2_frontend`) |
| `nginx` | nginx 1.29 | routing in `nginx/snippets/celebobo-routes.conf`, servers in `nginx/templates-*` |
| `certbot` | certbot (prod) | renews certificates every 12 h; nginx reloads every 6 h |

Measured memory with `WEB_CONCURRENCY=2`, `CELERY_CONCURRENCY=1`: api 180 MB, worker 115 MB, beat 90 MB,
frontend 60 MB, nginx 12 MB — about 460 MB for the whole application.

## Local

Requirements: Docker with Compose v2, both repositories side by side:

```
Documents/
  shopproject_v2/            # this repository
  shopproject_v2_frontend/
```

```bash
./deploy/local.sh up          # builds the image, starts everything, runs migrations
./deploy/local.sh seed        # demo catalogue, orders, sales, accounts (password: Boutique-Kin#2026)
cd ../shopproject_v2_frontend && npm run dev   # then open http://localhost:8080
```

- `deploy/.env.local` is created from `.env.local.example` on the first run. It works as-is; add the
  Cloudinary keys to test image uploads, a Gemini key (`ASSISTANT_PROVIDER=gemini`) to test the real assistant.
- Open the site at **http://localhost:8080**, not :3000: nginx sends `/api` and `/ws` to Django and the rest
  to the Next dev server, exactly like production. Frontend `.env.local`: `NEXT_PUBLIC_API_URL=/api/v1`,
  `NEXT_PUBLIC_WS_URL=/ws/`, `API_PROXY_TARGET` empty.
- To run the built frontend instead of the dev server:
  `FRONTEND_HOST=frontend:3000 ./deploy/local.sh --profile frontend up -d --build`.
- Emails (verification, password reset, notifications) land in Mailpit: http://localhost:8025.
- Postgres is reachable from the host on port 55432 (`celebobo` / `celebobo`).

| Command | Effect |
|---|---|
| `./deploy/local.sh e2e` | empty the database and load the fixed end-to-end data set; same ids and slugs every run (see below) |
| `./deploy/local.sh logs api` | follow one service (`worker`, `nginx`…) |
| `./deploy/local.sh ps` | status |
| `./deploy/local.sh manage createsuperuser` | any `manage.py` command |
| `./deploy/local.sh up` | rebuild after backend changes (migrations run automatically) |
| `./deploy/local.sh down` | stop, keep the data |
| `./deploy/local.sh reset` | stop and delete the database, Redis and documents |

### End-to-end data set

`./deploy/local.sh e2e` (or `manage.py seed_demo --e2e` where `E2E_SEED_ALLOWED=true`) empties the database and
creates, with the password `Boutique-Kin#2026` (`--password` to change it):

| | |
|---|---|
| Accounts | `admin@e2e.celebobo.test`, `responsable@e2e.celebobo.test` (manager), `revendeur@e2e.celebobo.test` (reseller, referral code `4821`), `client@e2e.celebobo.test` (invited by the reseller, default address) |
| Products | `galaxy-a55` (on sale 300 → 250), `redmi-note-13` (out of stock), `iphone-15` (variants Noir / Bleu), `ecouteurs-bluetooth` |
| Categories | `smartphones`, `audio` |
| Promotions | coupon `E2E10` (−10 %), shipping zones `Bukavu` and `Goma` (3 $, 24 h) and `Reste du pays` (7,50 $, the default) |

Emails sent by the tests (verification, password reset) are in Mailpit, which also has an API for Playwright:
`GET http://localhost:8025/api/v1/messages`.

## Production on a VPS

### 1. Server

- **Size:** 2 vCPU / 4 GB RAM is comfortable (`WEB_CONCURRENCY=3`, `CELERY_CONCURRENCY=2`, about 1 GB used);
  2 GB works with `WEB_CONCURRENCY=2`. Never below 1 GB.
- **Region:** close to the database and Redis, because every request talks to them. Supabase is in
  `eu-west-1` (Ireland) and Aiven Redis in Amsterdam: a server in **Amsterdam** or **Frankfurt** keeps each
  round trip at a few milliseconds (DigitalOcean AMS3 sits next to the Aiven instance).
- Ubuntu 24.04, Docker Engine with the Compose plugin
  (`curl -fsSL https://get.docker.com | sh`), a firewall allowing only 22, 80 and 443:
  `ufw allow OpenSSH && ufw allow 80,443/tcp && ufw enable`.

### 2. DNS

Point an `A` record for `DOMAIN` (and every name in `EXTRA_DOMAINS`, e.g. `www`) to the server's IP.
If you use Cloudflare, keep the records **DNS only** (grey cloud) for the first certificate.

### 3. Code and configuration

```bash
git clone <backend repo> shopproject_v2
git clone <frontend repo> shopproject_v2_frontend
cd shopproject_v2
cp deploy/.env.prod.example deploy/.env.prod   # fill every empty value
```

- `DOMAIN`, `EXTRA_DOMAINS`, `LETSENCRYPT_EMAIL`, and `DJANGO_ALLOWED_HOSTS` / the three `*_ORIGINS` lists with the same names.
- Database and Redis: the same Supabase pooler and Aiven URLs as before.
- `DJANGO_SECRET_KEY`: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`.
- Google sign-in: add `https://DOMAIN/connexion/google` as an authorised redirect URI in the Google console.
- Frontend on Vercel instead: remove `COMPOSE_PROFILES=frontend`, give the API its own name
  (`DOMAIN=api.celebobo.com`) and set the Vercel project's `API_PROXY_TARGET=https://api.celebobo.com`
  and `NEXT_PUBLIC_WS_URL=wss://api.celebobo.com/ws/`. The single-domain setup above is faster and simpler.

### 4. Start

```bash
./deploy/prod.sh certs     # first time only: Let's Encrypt certificate (ports 80/443 must be free)
./deploy/prod.sh up        # builds both images, migrates, starts everything
./deploy/prod.sh ps
curl https://DOMAIN/health/ready/
```

Then, once:
- `./deploy/prod.sh manage createsuperuser` (or keep the existing accounts: the database is the same);
- `POST /api/v1/bo/embeddings/reindex/` as an admin, if the assistant index is empty;
- run once in the Supabase SQL editor (the pooler ignores per-connection options):
  `alter role postgres set statement_timeout = '15s';`

### 5. Update

```bash
git -C ../shopproject_v2_frontend pull && git pull
./deploy/prod.sh up        # rebuilds, runs new migrations, restarts changed containers
```

Roll back by checking out the previous commit and running `./deploy/prod.sh up` again.

### 6. Postgres and Redis on the server

Every request talks to the database and Redis several times: hosted in another data centre, each trip
costs 30 ms or more, and opening a connection several seconds at worst. On the server, a query costs
about 0.2 ms. The profile `data` adds `postgres` (pgvector 17, ~1 GB of shared buffers), `redis`
(password, 512 MB, only cache keys may be evicted) and `backup`; none of them is published on the host.

Moving from Supabase, once (the site is stopped for a few minutes):

1. In `.env.prod`: `COMPOSE_PROFILES=data`, `POSTGRES_PASSWORD` and `REDIS_PASSWORD` (hex, see the
   example), `SOURCE_DATABASE_URL` = the Supabase URL on its **session** pooler (port `5432`), then the
   local URLs: `DATABASE_URL=postgres://celebobo:<POSTGRES_PASSWORD>@postgres:5432/celebobo`,
   `DATABASE_POOLER=false`, `DATABASE_CONN_MAX_AGE=300`, `REDIS_*_URL=redis://:<REDIS_PASSWORD>@redis:6379/0|1|2`.
2. `./deploy/prod.sh import-db`: stops the application, starts Postgres and Redis, builds the schema with
   the migrations, then copies every row from Supabase (data only, sequences included).
3. `./deploy/prod.sh compare-db`: the row count of every table, Supabase against local, must be identical.
4. `./deploy/prod.sh up`, then empty `SOURCE_DATABASE_URL`.

Supabase is never written to: to go back, restore the previous URLs and run `./deploy/prod.sh up`
(what was written meanwhile stays on the server only). Redis keeps nothing to copy.

**Backups**: `backup` dumps the database every night at 03:00 (Bukavu time) into `deploy/backups/`
and keeps `BACKUP_DAYS` days. `./deploy/prod.sh backup` makes one now. Copy them off the server too
(another machine, a storage bucket): a dump on the same disk does not survive the loss of the server.
Restore one with:

```bash
./deploy/prod.sh stop api worker beat
./deploy/prod.sh exec -T postgres pg_restore --clean --if-exists -U celebobo -d celebobo < deploy/backups/<file>.dump
./deploy/prod.sh up
```

### Operations

| Task | Command |
|---|---|
| Logs | `./deploy/prod.sh logs api` (`worker`, `nginx`, `frontend`…); rotated at 5 × 20 MB per service |
| Django shell | `./deploy/prod.sh manage shell` |
| Restart one service | `./deploy/prod.sh restart worker` |
| Health | `/health/live/` (process up), `/health/ready/` (database, cache, broker) |
| Certificates | renewed automatically; check with `./deploy/prod.sh logs certbot` |
| Backups | with the profile `data`, nightly dumps in `deploy/backups/` (see 6); hosted, Supabase keeps its own; images live in Cloudinary |

Every response carries `Server-Timing: app;dur=…`: the time spent in Django, to compare with the total time
in the browser's Network tab.
