# --- STAGE 1: Base ---
FROM python:3.14.2-slim-trixie AS base
ENV APP_HOME=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    UV_CACHE_DIR=/tmp/.uv_cache

WORKDIR $APP_HOME
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN groupadd -r app && useradd -r -g app app

# Copy shared-core (common dep)
COPY --chown=app:app ./services/shared-core /app/shared-core

# --- TARGET: Image Processor Worker ---
FROM base AS processor
RUN apt-get update && apt-get install -y --no-install-recommends \
    libwebp-dev libjpeg-dev libpng-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=app:app ./services/image-processor /app
RUN chown -R app:app /app && \
    su app -s /bin/sh -c "uv sync --frozen --no-dev --no-install-project"

USER app
CMD ["uv", "run", "python", "-m", "image_processor.main"]

# --- TARGET: Email Notification Worker ---
FROM base AS notification
COPY --chown=app:app ./services/email-notification /app
RUN chown -R app:app /app && \
    su app -s /bin/sh -c "uv sync --frozen --no-dev --no-install-project"

USER app
CMD ["uv", "run", "python", "-m", "email_notification.main"]
