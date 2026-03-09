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
    libpq5 curl && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app app
RUN chown app:app /app
USER app

ENV UV_CACHE_DIR=/tmp/.uv_cache

# Create the directory structure for the path dependency
# This allows uv to resolve the metadata before you copy the full source
COPY --chown=app:app ./services/shared-core /app/services/shared-core
COPY --chown=app:app ./services/email-notification /app/services/email-notification

WORKDIR /app/services/email-notification

RUN uv sync --frozen --no-dev --no-install-project

# Set the command to run the worker
# We use 'uv python -m' to ensure the module is found within the virtualenv context
CMD ["uv", "run", "python", "-m", "email_notification.main"]
