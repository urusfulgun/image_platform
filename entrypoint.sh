#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

logger() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $1"
}

# --- Configuration ---
# These can be overridden by Docker environment variables
# --- 1. Load Environment Variables ---
if [ -f .env ]; then
    logger "Loading environment variables from .env..."
    # Export variables, ignoring lines starting with # and empty lines
    set -a # automatically export all variables
    source .env
    set +a
else
    logger "No .env file found, relying on container environment."
fi

# --- 2. Test connection to Kafka ---
# This invokes test connection to Kafka
logger "Testing connection to Kafka..."
uv run --env-file=.env python src/bin/check_ssl_kafka.py

logger "Starting the application..."
exec "$@"
