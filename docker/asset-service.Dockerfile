# --- STAGE 1: Base (Shared) ---
FROM python:3.14.2-slim-trixie AS base
ENV APP_HOME=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR $APP_HOME
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# --- STAGE 2: Development (DevContainer Target) ---
FROM base AS development
# Install dev-only tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl gcc libpq-dev sudo bash-completion make && \
    rm -rf /var/lib/apt/lists/*

# Create vscode user with sudo
ARG USERNAME=vscode
RUN groupadd --gid 1000 $USERNAME && \
    useradd --uid 1000 --gid 1000 -m $USERNAME && \
    echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME

USER $USERNAME
# "Usable Bash" configurations
RUN echo 'eval "$(uv generate-shell-completion bash)"' >> ~/.bashrc && \
    echo 'export PS1="\[\e[32m\]\u@dev\[\e[m\]:\[\e[34m\]\w\[\e[m\]\$(if [ -n \"\$VIRTUAL_ENV\" ]; then echo \" \[\e[33m\](\$(basename \"\$VIRTUAL_ENV\"))\[\e[m\]\"; fi) \$ "' >> ~/.bashrc && \
    echo 'if [ -d "$APP_HOME/.venv" ]; then source "$APP_HOME/.venv/bin/activate"; fi' >> ~/.bashrc

# --- STAGE 3: Production (Final Image) ---
FROM base AS production
# Install only runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*


# Create system user
RUN groupadd -r app && useradd -r -g app app
RUN chown app:app /app
USER app

ENV UV_CACHE_DIR=/tmp/.uv_cache

# Copy application code
COPY --chown=app:app ./services/asset-service $APP_HOME
RUN uv sync --frozen --no-dev --no-install-project
