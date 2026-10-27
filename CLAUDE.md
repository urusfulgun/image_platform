# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Image Platform: users create projects, upload images straight to S3 (RustFS), and background workers convert them to AVIF and email a notification when they're done. Polyglot monorepo run through `docker-compose.yaml` on the `image-platform-network` network. The devcontainer joins that network, so hostnames such as `kafka`, `rustfs` and `keycloak` resolve from inside it. `plan.md` holds the original design brief.

## Product docs

- @docs/product/mission.md
- @docs/product/roadmap.md
- @docs/product/tech-stack.md

## Workflow rule

Every non-trivial change starts with a spec in docs/specs/YYYY-MM-DD-<slug>/ containing spec.md and tasks.md.

## Folder structure

```
services/
  shared-core/         library (DTOs, security schemas, Kafka/Debezium events, errors, S3 key helpers)
  asset-service/       FastAPI on Granian: projects, images, pre-signed URLs, RustFS callback, user sync
  bff-token-handler/   FastAPI on Granian: OAuth BFF, sessions in Redis, DPoP proxy to asset-service
  image-processor/     worker: raw image -> AVIF + preview
  email-notification/  worker: SMTP to Mailpit on image.avif.ready
  cleanup-buckets/     worker: deletes an image's S3 objects on image.all.deleted
  frontend/            Angular 21 SPA (Bun)
docker/                one Dockerfile per service (build context is the repo root)
config/                nginx-proxy, debezium (register-connectors.sh), grafana_alloy
init-db/               SQL run on first Postgres init (no migrations)
secrets/, persistent_data/   gitignored, required at runtime (realm import, DB passwords, BFF client secret)
```

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
UIs: nginx `http://image-platform` (80; needs `127.0.0.1 image-platform` in `/etc/hosts`), Keycloak `:8080`, Kafka UI `:8081`, Debezium Connect `:8083`, RustFS `:9000`/console `:9001`, Mailpit `:8025`, pgAdmin `:8888`.

### Python services (uv, Python ≥ 3.14.2)
Each service is its own uv project with its own `.venv` and `uv.lock`. Run from the service directory:
```bash
cd services/<service>
uv sync --extra dev                          # test deps are an optional extra named "dev", not a dependency group
uv run --extra dev pytest                    # whole suite
uv run --extra dev pytest tests/test_logout.py::test_name -q   # single test
ruff check . && ruff format .                # lint/format (ruff installed as a uv tool)
mypy --strict src
```
Async tests use `@pytest.mark.asyncio` explicitly (no `asyncio_mode` configured). Tests mock Redis, DB, Kafka and S3 with `AsyncMock`/`pytest-mock` and don't need the running stack.

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

## Key conventions

- **Request path:** `Browser → nginx-proxy → { /api/* → bff-token-handler, /auth/* → keycloak, else → SPA }`. nginx strips `/api`, so BFF routes are `/login`, `/authorization-code/callback`, `/logout`, `/me`, `/proxy/{path}`.
- **BFF Token Handler:** the browser never holds OAuth tokens. The BFF (confidential client `bff-client`) runs Auth Code + PKCE, stores the `TokenSet` and DPoP key pair in Redis under a random session id, and sets an HttpOnly, SameSite=Strict `sid` cookie. Cookie attributes must stay identical between `set_cookie` and `delete_cookie`. Everything lives on `app.state`, created in `lifespan` in `main.py`.
- **DPoP:** every upstream call to AssetService gets a fresh proof with an `ath` claim (`bff_token_handler/proxy/reverse_proxy.py`). RS-side validation helper: `shared_core/utils/endpoint/rs_dpop.py`.
- **Shadow users:** AssetService identifies the user via `X-User-Sub` (`asset_service/api/deps.py`) and resolves a local `UserModel` by `kc_sub`, returning 404 "User not synced yet" if missing. Users arrive by CDC: Debezium on Keycloak `public.user_entity` → Kafka topic `keycloak-users` → `asset_service/kafka/consumer.py` / `user_sync_handler.py`. Only `register-connectors.sh` is mounted; the `copy*` variants are scratch.
- **Image pipeline topics:** pre-signed PUT to bucket `raw-images` → RustFS webhook `POST /callback/rustfs` (`api/s3_callbacks.py`) → `image.raw.uploaded` → image-processor writes to `processed-images` and emits `image.avif.ready` (failures to DLQ `image.raw.failed`) → consumed by AssetService (`lifespans/image_status.py`, status `OPTIMIZED`) and email-notification. Deletions emit `image.all.deleted`, which cleanup-buckets consumes to remove the raw, processed and preview objects. Raw objects are not pruned after processing.
- **Events:** all payloads are Pydantic models in `shared_core/events/kafka_events.py`. Change producers and consumers together.
- **shared-core** is an editable path dependency of every Python service (`[tool.uv.sources] shared-core = { path = "../shared-core", editable = true }`). Changes affect every service.
- **asset-service layering:** `api/` → `dependencies/` → `domain/` (`ProjectService`, `ImageService`) → `db/` (async SQLAlchemy + asyncpg). Register background resources (Kafka, S3) on the `LifespanManager` in `lifespans/hub.py`, not in `main.py`.
- **Workers** are aiokafka consumer loops with a small FastAPI `/health` endpoint.
- **DB schema:** no migrations. A schema change needs `init-db/postgres-image-metadata/*.sql` and `db/models.py` updated together, plus a fresh volume.
- **Docker builds:** each Python Dockerfile copies `services/shared-core` next to the service and runs `uv sync --frozen --no-dev`. Run `uv lock` after changing dependencies or the build fails.
