# Tech stack

Last reviewed: 2026-10-27. "Current" is verified from lock files, compose and Dockerfiles; anything not verifiable is marked *unverified*.

## Current

### Runtime & languages
| Component | Version | Source |
|---|---|---|
| Python | 3.14.2 (`.python-version`, `requires-python >=3.14.2`, image `python:3.14.2-slim-trixie`) | pyproject / Dockerfiles |
| Python (devcontainer) | 3.14.8 | `.devcontainer/devcontainer.json` |
| uv | `ghcr.io/astral-sh/uv:latest` in Dockerfiles (floating); build backend `uv_build >=0.10,<0.11` | Dockerfiles / pyproject |
| TypeScript | 5.9.3 | bun.lock |
| Bun | 1.3.9 (`packageManager`); build image `oven/bun:1` (floating minor) | package.json / nginx-proxy.Dockerfile |

### Python services (locked versions)
| Library | asset-service | bff-token-handler | workers (image-processor, email-notification, cleanup-buckets) | shared-core |
|---|---|---|---|---|
| FastAPI | 0.162.0 | 0.135.1 | 0.135.1 | 0.135.1 |
| ASGI server | granian 2.7.1 | granian 2.7.1 | uvicorn 0.41.0 (health endpoint only) | — |
| Pydantic / pydantic-settings | 2.12.5 / 2.13.1 | same | same | same |
| aiokafka | 0.13.0 | 0.13.0 (transitive) | 0.13.0 | 0.13.0 |
| python-keycloak | 7.1.1 (sync calls) | 7.1.1 (sync calls) | 7.1.1 (transitive) | 7.1.1 |
| PyJWT | 2.15.1 | 2.11.0 | 2.11.0 | 2.11.0 |
| cryptography | 46.0.5 | 46.0.5 | 46.0.5 | 46.0.5 |
| httpx | 0.28.1 | 0.28.1 | 0.28.1 | 0.28.1 |
| S3 client | boto3 1.42.54 (sync) | — | aioboto3 15.5.0 (boto3 1.40.61) | — |
| Other | SQLAlchemy 2.0.46 + asyncpg 0.31.0 | redis 7.2.0 | Pillow 12.1.1 + pillow-avif-plugin 1.5.5 (image-processor); aiosmtplib 5.1.0 (email) | — |

Dependency constraints are `>=` only, without upper bounds; only `uv.lock` pins versions. `shared-core` is an editable path dependency of every service.

### Frontend (`services/frontend`)
Angular 21.1.5 (core, Material/CDK 21.1.5; CLI/build 21.1.4), standalone + zoneless, signals for state, rxjs 7.8.2, Tailwind 4.2.0, @transcend-io/conflux 6.1.3 (ZIP download). Tests: Vitest 4.0.18 + jsdom 27.4.0 (1 spec, broken), Playwright 1.64.0 (e2e with mocked BFF).

### Infrastructure (docker-compose)
| Component | Image |
|---|---|
| Postgres (Keycloak, asset metadata) | `postgres:17-alpine` |
| Keycloak | `quay.io/keycloak/keycloak:26.5.4` (`start-dev`) |
| Redis | `redis:7.4-alpine` (no volume) |
| Kafka (KRaft) | `confluentinc/cp-kafka:latest` |
| Kafka UI | `provectuslabs/kafka-ui:latest` (unmaintained) |
| Debezium Connect | `debezium/connect:2.7.3.Final` |
| Connector registration | `curlimages/curl:latest` |
| Object storage | `rustfs/rustfs:1.0.0-alpha.83` |
| Mail | `axllent/mailpit:latest` |
| pgAdmin | `dpage/pgadmin4` (no tag) |
| Reverse proxy + SPA | `nginx:stable-alpine` (floating) |
| Logs | `grafana/loki:main-e569e10` (dev build), `grafana/alloy:v1.14.0`, `grafana/grafana:12.3` |

### Tooling
- **DB schema**: `init-db/postgres-image-metadata/*.sql` on first init only; no migrations.
- **Lint/format**: one root `ruff.toml` (`required-version >=0.17.2`, line length 88, py314). Rules: E, W, F, I, UP, B, SIM, RUF, S, T20, ASYNC, with S101/S105/S106 ignored in tests. The tree is clean for `ruff check` and `ruff format --check`. Format commits are listed in `.git-blame-ignore-revs`. Not enforced yet (F8). ruff is installed as a uv tool, not locked.
- **Type checking**: mypy in the editor; no config, not enforced. Version *unverified*.
- **Tests**: pytest 9.0.2, pytest-asyncio 1.3.0, pytest-mock; no pytest config, no coverage. asset-service has API characterization tests (`tests/api/`, httpx ASGITransport against in-memory aiosqlite, with a `known_bug` marker). email-notification and cleanup-buckets have characterization tests with fake Kafka, S3 and SMTP clients.
- **CI**: none.
- **Dependency updates**: manual.

## Target

### Tooling
- **CI**: GitHub Actions, using a per-service matrix to run ruff, mypy and pytest for the Python services, and the build, Vitest and Playwright for the frontend, on every PR.
- **Lint/format**: one shared root `ruff.toml` with an agreed rule set, enforced in CI.
- **Type checking**: `mypy --strict` per service, enforced in CI. Existing errors get fixed gradually.
- **Tests**: add `[tool.pytest.ini_options]` and `pytest-cov` to each service. Every service must have tests. Fix the broken Vitest spec. The stack stays pytest, Vitest and Playwright.
- **Dependency updates**: Renovate or Dependabot opens PRs for `uv.lock`, `bun.lock` and Docker image tags, and CI gates them.
- **DB schema**: Alembic migrations for asset-service replace the `init-db` SQL.

### Runtime and libraries
- **Python**: follow the latest 3.14.x patch release, and keep the Docker images in line with the devcontainer.
- **S3**: asset-service moves to aioboto3, with one shared client created in the S3 lifespan, matching the workers.
- **Keycloak**: the BFF uses python-keycloak's async `a_*` methods. `rs_dpop` validates tokens with PyJWT against a cached JWKS instead of making blocking Keycloak calls on each request.
- **AVIF**: use Pillow's built-in AVIF support and drop `pillow-avif-plugin`.
- **ASGI servers**: no change. Granian stays for the HTTP services and uvicorn stays for the worker health endpoints.
- **Frontend**: stay on Angular 21, TypeScript 5.9, Vitest, Playwright and Bun, taking patch-level updates only.

### Infrastructure
- **Image tags**: pin exact versions for every image, including `uv`. This means no `:latest`, no untagged images and no dev builds such as Loki's `main-*` tag.
- **Debezium**: upgrade to 3.x from quay.io and re-test the connector config.
- **Kafka UI**: replace `provectuslabs/kafka-ui` with `kafbat/kafka-ui`.
- **Object storage**: stay on RustFS, moving to a stable tag once one is released. The code stays S3-generic.
