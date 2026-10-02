FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .
COPY --chown=app:app deploy-real-prod/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN DJANGO_SECRET_KEY=collectstatic DJANGO_ALLOWED_HOSTS=localhost \
        python manage.py collectstatic --noinput \
    && mkdir -p /app/var/documents \
    && chown -R app:app /app/var /app/staticfiles \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health/live/', timeout=4)" || exit 1

ENTRYPOINT ["tini", "--", "docker-entrypoint.sh"]
CMD ["api"]
