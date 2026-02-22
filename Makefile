# Variables
COMPOSE_CMD := docker compose
SERVICES := postgres-keycloak keycloak bff-token-handler rustfs asset-service redis-session image-processor notification-worker nginx-proxy mailpit

.PHONY: up down restart status logs clean help

## up: Start only Postgres and Keycloak in the background
up:
	@echo "Starting $(SERVICES)..."
	$(COMPOSE_CMD) up -d --build $(SERVICES)

## down: Stop and remove the containers
down:
	@echo "Stopping $(SERVICES)..."
	$(COMPOSE_CMD) stop $(SERVICES)

## restart: Restart the Postgres and Keycloak services
restart:
	@echo "Restarting services..."
	$(COMPOSE_CMD) restart $(SERVICES)

## status: Check the status of the specific services
status:
	$(COMPOSE_CMD) ps $(SERVICES)

## logs: Follow logs for the specific services
logs:
	$(COMPOSE_CMD) logs -f $(SERVICES)

## clean: Stop services and remove their volumes (WARNING: Deletes database data)
clean:
	$(COMPOSE_CMD) down -v

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'
