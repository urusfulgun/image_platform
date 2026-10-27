# Roadmap

Derived from [mission.md](mission.md) and [tech-stack.md](tech-stack.md). Each item becomes one spec in `docs/specs/YYYY-MM-DD-<slug>/`. Sizes: S ≈ under a day, M ≈ a few days, L ≈ a week or more.

Items run in order within each phase. Characterization tests come first so that later refactors can be checked against them. The security fixes (R1–R4) start Phase 2 because the mission requires closing known holes before anything is showcased.

## Phase 1: Foundation

- [x] F1 [M] Characterization tests for the asset-service API: projects, presign, delete and the RustFS callback
- [x] F2 [M] Characterization tests for the BFF: login, callback, `/me` and the proxy, including current header forwarding
- [x] F3 [S] Characterization tests for `rs_dpop` token and DPoP validation
- [x] F4 [M] First tests for the email-notification and cleanup-buckets workers
- [x] F5 [S] Shared root `ruff.toml`, with existing findings fixed
- [ ] F6 [M] `mypy --strict` config per service, with the current errors recorded as a baseline
- [ ] F7 [S] Pytest config and `pytest-cov` in every service, plus a fix for the broken Vitest spec
- [ ] F8 [M] GitHub Actions CI: Python matrix (ruff, mypy, pytest) plus frontend build, Vitest and Playwright
- [ ] F9 [S] Pin every image tag, including `uv`, and fix the misnamed `.dockerignore` files
- [ ] F10 [S] Renovate or Dependabot for `uv.lock`, `bun.lock` and Docker tags
- [ ] F11 [S] Security scanning in CI with pip-audit and Trivy
- [ ] F12 [S] Move `.python-version`, `requires-python` and the base images to the latest Python 3.14.x
- [ ] F13 [M] Upgrade Debezium to 3.x (quay.io) and re-test the `keycloak-user-sync` connector
- [ ] F14 [S] Replace `provectuslabs/kafka-ui` with `kafbat/kafka-ui`
- [ ] F15 [S] Drop `pillow-avif-plugin` and use Pillow's built-in AVIF support
- [x] F16 [S] Fix the init SQL (missing commas) so a fresh install works
- [ ] F17 [M] End-to-end smoke test against the running stack (pytest + Playwright): login through Keycloak and the BFF, upload an image until it is `OPTIMIZED`, and check each worker's `/health`. Credentials come from env until N9. (A Keycloak user `smoke-test` and a throwaway Node Playwright script from the F5 check already exist as a starting point. Needs F18 for the upload to reach `OPTIMIZED` without a hand-sent webhook.)
- [ ] F18 [S] Provision the RustFS webhook target and the `raw-images` ObjectCreated/ObjectRemoved notification as code (for example a one-shot init container, like `debezium-configurator`), using `RUSTFS_WEBHOOK_TOKEN`. Today neither exists, so uploads stay `PENDING`.

## Phase 2: Refactors

- [ ] R1 [M] Close the `X-User-Sub` impersonation hole: identity comes from the validated token's `sub`, and the proxy strips client identity, DPoP and `Cookie` headers
- [ ] R2 [M] Load secrets from files or env; remove the hardcoded BFF client secret, S3 keys, webhook token and DB URL. (F5 already moved the asset-service S3 keys, the webhook token and the BFF client secret to required settings. Still open: the DB URL, the worker S3 keys and the compose dev defaults.)
- [ ] R3 [S] Stop logging tokens, cookies, PKCE values and full request headers
- [ ] R4 [S] RustFS webhook auth: secret from env, constant-time compare, 403 on malformed headers. (F5: the token already comes from `RUSTFS_WEBHOOK_TOKEN`.)
- [ ] R5 [M] Harden `rs_dpop`: check `iss`/`aud`, enforce an `iat` window, add a `jti` replay cache, check `typ`, fix the `htu` query-string mismatch, and return generic 401 details without re-wrapping
- [ ] R6 [M] BFF refreshes the access token before proxying
- [ ] R7 [M] Async Keycloak calls in the BFF and a cached JWKS in `rs_dpop`
- [ ] R8 [S] An expired session returns 401 instead of 500; the PKCE state is single-use
- [ ] R9 [M] Switch asset-service to aioboto3, with one shared client from the S3 lifespan
- [ ] R10 [M] Alembic migrations replace `init-db` SQL
- [ ] R11 [S] Workers read topics and S3 credentials from env instead of hardcoded values
- [ ] R12 [S] Remove dead code and scratch files (`register-connectors copy*.sh`, unused Dockerfiles, `main_no_preview.py`, dead frontend files). (F5 removed the workers' hello-world `main()` stubs and `[project.scripts]`.)
- [ ] R13 [S] A DLQ consumer marks failed images `FAILED` instead of leaving them `PENDING`
- [ ] R14 [S] Poison messages and Debezium tombstones no longer kill consumers
- [ ] R15 [M] Idempotent image processing with deterministic output keys (no orphans or duplicate emails on redelivery)
- [ ] R16 [M] Frontend auth cleanup: drop the `Bearer null` interceptor, use relative API URLs, add route guards
- [ ] R17 [S] BFF proxy filters upstream response headers (hop-by-hop, `content-encoding`/`content-length`) instead of copying them verbatim
- [ ] R18 [S] BFF generates a fresh DPoP key pair per session at callback instead of sharing one process-wide key
- [ ] R19 [S] Workers stop losing failures: S3/SMTP errors and failed DLQ sends go to a DLQ or retry instead of being committed, and `/health` reflects the real consumer state
- [ ] R20 [S] BFF `/me` stops returning 500 when the ID token's email fails `EmailStr` validation (for example a reserved `.local` domain): accept or relax the field, or return a clean 4xx, and test it

## Phase 3: New features

- [ ] N1 [M] Threat model document (STRIDE): assets, trust boundaries, mitigations, known gaps
- [ ] N2 [M] Security test suite: impersonation, DPoP replay, expired tokens, webhook auth
- [ ] N3 [S] nginx security headers: CSP, HSTS, Permissions-Policy
- [ ] N4 [M] Email the image owner: the event carries the user ID and the worker looks up their email
- [ ] N5 [M] Right to erasure: deleting a Keycloak user cascades to their projects, DB rows and S3 objects
- [ ] N6 [M] Data export: a user downloads all of their projects and images
- [ ] N7 [M] Retention limits: prune raw images after AVIF conversion; TTLs for Kafka topics and logs
- [ ] N8 [M] README with an architecture diagram and a one-command quickstart
- [ ] N9 [S] Seeded demo realm and user, so `make up` gives a working login
- [ ] N10 [S] Grafana provisioned with a Loki datasource and a pipeline dashboard
- [ ] N11 [S] UI shows failed images and offers a retry
