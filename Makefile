# Variables
COMPOSE_CMD := docker compose
SERVICES := kafka kafka-ui debezium debezium-configurator postgres-keycloak postgres-asset-metadata keycloak bff-token-handler rustfs asset-service redis-session image-processor notification-worker nginx-proxy mailpit pgadmin cleanup-buckets-worker

PYTHON_SERVICES := shared-core asset-service bff-token-handler image-processor email-notification cleanup-buckets

.PHONY: up down restart status logs clean typecheck test help

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

## typecheck: Run mypy in every Python service and compare with its mypy-baseline.txt
typecheck:
	@status=0; for s in $(PYTHON_SERVICES); do \
		echo "== $$s"; \
		(cd services/$$s && uv run --quiet --extra dev python ../../scripts/mypy_check.py) || status=1; \
	done; exit $$status

## test: Run pytest with coverage in every Python service; fails below its fail_under floor
test:
	@status=0; for s in $(PYTHON_SERVICES); do \
		echo "== $$s"; \
		(cd services/$$s && uv run --quiet --extra dev pytest --cov) || status=1; \
	done; exit $$status

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'
