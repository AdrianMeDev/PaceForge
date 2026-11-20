# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system --gid 10001 paceforge \
    && useradd --system --uid 10001 --gid paceforge --no-create-home --shell /usr/sbin/nologin paceforge

# pg_dump and pg_restore for the encrypted backups (PostgreSQL 17 on Debian Trixie, matching db).
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o paceforge -g paceforge -m 0700 /backups

WORKDIR /app
COPY --from=builder --chown=paceforge:paceforge /app /app

USER paceforge
EXPOSE 8000

# The Host header must be an allowed host, so use the first entry of DJANGO_ALLOWED_HOSTS,
# then APP_DOMAIN, then localhost.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; host = (os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')[0].strip() or os.environ.get('APP_DOMAIN', '').strip() or 'localhost'); urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/health/', headers={'Host': host}), timeout=4)"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
