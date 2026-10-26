# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Image Platform: users create projects, upload images straight to S3 (RustFS), and background workers convert them to AVIF and email a notification when they're done. It's a polyglot monorepo. The Python services live under `services/` and the Angular SPA lives in `services/frontend`. Everything runs together through `docker-compose.yaml` on the `image-platform-network` network, and the devcontainer joins that network too, so service hostnames such as `kafka`, `rustfs` and `keycloak` resolve from inside it. `plan.md` holds the original design brief: use cases, pipeline stages and DB plan.

## Commands

### Full stack (Docker Compose, via Makefile)
```bash
make up        # docker compose up -d --build <all services>
make down      # stop services
make logs      # follow logs
make status
make clean     # docker compose down -v (wipes volumes)
docker compose up -d --build asset-service   # rebuild a single service
```
Useful UIs: nginx entrypoint `http://localhost` (port 80), Keycloak `:8080`, Kafka UI `:8081`, Debezium Connect `:8083`, RustFS `:9000`/console `:9001`, Mailpit `:8025`, pgAdmin `:8888`.

### Python services (uv, Python ≥ 3.14.2)
Each service is its own uv project with its own `.venv` and `uv.lock`. Run commands from the service directory:
```bash
cd services/<service>
uv sync --extra dev                          # test deps are an optional extra named "dev", not a dependency group
uv run --extra dev pytest                    # whole suite
uv run --extra dev pytest tests/test_logout.py::test_name -q   # single test
ruff check . && ruff format .                # lint/format (ruff installed as a uv tool)
mypy --strict src                            # editor runs mypy in --strict mode
```
Async tests use `@pytest.mark.asyncio` explicitly, since no `asyncio_mode` is configured. Tests mock Redis, the DB session, Kafka and S3 with `AsyncMock`/`pytest-mock`. They don't need the running stack.

### Frontend (Angular 21 + Bun)
```bash
cd services/frontend
bun install
bun run start     # ng serve on :4200
bun run build
bun run test      # Vitest via ng test
bun run e2e       # Playwright (e2e/), run `bun run e2e:install` first
```
Prettier config is in `package.json`: printWidth 100, single quotes.

## Architecture

### Request path and security (BFF Token Handler pattern)
`Browser → nginx-proxy → { /api/* → bff-token-handler, /auth/* → keycloak, else → SPA }`.
- nginx strips the `/api` prefix, so BFF routes are `/login`, `/authorization-code/callback`, `/logout`, `/me` and `/proxy/{path}`.
- **The browser never holds OAuth tokens.** The BFF is a confidential Keycloak client (`bff-client`). It runs Authorization Code + PKCE, with the PKCE verifier stored in Redis by `state`. It keeps the `TokenSet` and the DPoP key pair in Redis under a random session id and sets an HttpOnly, SameSite=Strict `sid` cookie. Cookie attributes must stay identical between `set_cookie` and `delete_cookie`.
- Tokens are **DPoP-bound**. The BFF generates an EC key pair at startup (`app.state.ec_key_pair`), and every upstream call to AssetService gets a fresh DPoP proof with an `ath` claim (`bff_token_handler/proxy/reverse_proxy.py`). The resource-server-side DPoP validation helper is in `shared_core/utils/endpoint/rs_dpop.py`.
- AssetService currently identifies the user from the `X-User-Sub` header (`asset_service/api/deps.py`). It then resolves a local **shadow user** by `kc_sub`, and returns 404 "User not synced yet" if that user hasn't arrived through the sync below.

### Shadow-user sync (CDC)
Keycloak Postgres runs with `wal_level=logical`. `debezium-configurator` runs `config/debezium/register-connectors.sh`, which registers a connector on `public.user_entity`. The connector unwraps and reroutes changes to the Kafka topic **`keycloak-users`**. AssetService consumes that topic (`asset_service/kafka/consumer.py`, `user_sync_handler.py`) and upserts `UserModel` rows. The `register-connectors copy*.sh` files are scratch variants, and the compose file only mounts `register-connectors.sh`.

### Image pipeline (Kafka topics)
1. AssetService issues **pre-signed S3 PUT URLs**, and the browser uploads directly to RustFS bucket `raw-images`.
2. A RustFS webhook calls `POST /callback/rustfs` on AssetService (`api/s3_callbacks.py`). `ObjectCreated` publishes `image.raw.uploaded`. `ObjectRemoved` marks the image deleted in the DB.
3. `image-processor` consumes `image.raw.uploaded`. It converts the image to AVIF plus a preview with Pillow, writes both to `processed-images`, and publishes `image.avif.ready`. Failures go to the DLQ `image.raw.failed`.
4. `image.avif.ready` is consumed by AssetService (`lifespans/image_status.py`, which sets status `OPTIMIZED` and stores the paths), by `email-notification` (SMTP to Mailpit) and by `cleanup-buckets` (prunes raw objects). AssetService also emits `image.all.deleted` for deletions.

All event payloads are Pydantic models in `shared_core/events/kafka_events.py`. When you change an event, update its producers and consumers together.

### Service internals
- **shared-core** is a library, not a service. Every other Python service pulls it in as an editable path dependency (`[tool.uv.sources] shared-core = { path = "../shared-core", editable = true }`). It holds the DTOs, security schemas (`TokenSet`, `UserSession`, `KeyPair`), Debezium event schemas, error types and S3 key helpers. Changes here affect every service.
- **asset-service** (FastAPI on Granian) is layered as `api/` (routers + `deps.py`) → `dependencies/` (DI providers) → `domain/` (`ProjectService`, `ImageService`) → `db/` (async SQLAlchemy + asyncpg). Startup resources such as the Kafka consumers/producer and the S3 client are registered as named async context managers on a custom `LifespanManager` in `lifespans/hub.py`. Add new background resources there rather than in `main.py`.
- **bff-token-handler** (FastAPI on Granian) keeps everything on `app.state`: the Redis session store, the PKCE verifier store, the Keycloak client and the DPoP key pair. All of it is created in `lifespan` in `main.py`.
- **Workers** (`image-processor`, `email-notification`, `cleanup-buckets`) are aiokafka consumer loops with a small FastAPI `/health` endpoint.
- **DB schema** for AssetService is created by `init-db/postgres-image-metadata/*.sql` on the container's first init. There are no migrations, so a schema change needs the SQL and `db/models.py` updated together, plus a fresh volume.

### Docker builds
The build context is always the repo root. Each Python Dockerfile copies `services/shared-core` next to the service so the relative path dependency resolves, then runs `uv sync --frozen --no-dev`. Keep `uv.lock` in sync (`uv lock`) after changing dependencies, or the image build fails. `persistent_data/` and `secrets/` are gitignored but required at runtime: the Keycloak realm import, the DB password secrets and the BFF client secret all live in `secrets/`.
