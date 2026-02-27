# --- STAGE 1: Base ---
FROM python:3.14.2-slim-trixie AS base
ENV APP_HOME=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR $APP_HOME
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# --- STAGE 2: Production ---
FROM base AS production
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app app
RUN chown app:app /app
USER app

ENV UV_CACHE_DIR=/tmp/.uv_cache

# Create the directory structure for the path dependency
# This allows uv to resolve the metadata before you copy the full source
COPY --chown=app:app ./services/shared-core /app/services/shared-core
COPY --chown=app:app ./services/asset-service /app/services/asset-service

WORKDIR /app/services/asset-service

RUN uv sync --frozen --no-dev --no-install-project

EXPOSE 8000
CMD ["uv", "run", "granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "asset_service.main:app"]
