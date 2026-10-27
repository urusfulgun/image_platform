# F5: Shared root `ruff.toml`, with existing findings fixed

## Goal
Give every Python service one pinned lint and format config at the repo root. Fix every finding it reports, so that F8 can gate `ruff check` and `ruff format --check` on a clean tree. Behaviour stays as it is, apart from the secret and stub changes listed under "Findings fixed with a behaviour change".

## Config (`/ruff.toml`)
- `required-version = ">=0.17.2"`, `target-version = "py314"`, `line-length = 88`
- `extend-exclude = ["services/frontend"]`. ruff's defaults already skip `.venv` and `node_modules`.
- `[lint] select = ["E", "W", "F", "I", "UP", "B", "SIM", "RUF", "S", "T20", "ASYNC"]`. This is explicit, so ruff's own default set has no effect.
- `[lint.per-file-ignores] "services/*/tests/**" = ["S101", "S105", "S106"]`. Tests use asserts and fake secrets.
- `[lint.flake8-bugbear] extend-immutable-calls = ["fastapi.Depends", "fastapi.Query", "fastapi.Header", "fastapi.Body", "fastapi.File"]`. This is the standard FastAPI B008 exemption.
- `[lint.isort] known-first-party` lists the six package names, so imports sort the same way whichever service directory ruff runs from.
- `[format]`: ruff defaults (double quotes, spaces).
- No `[tool.ruff]` in any service `pyproject.toml`. Ruff finds the root file from each service directory.

Baseline at 88 with this rule set: about 180 lint findings, roughly 120 auto-fixable, and 39 files to reformat.

## Findings fixed without a behaviour change
| Rule | Fix |
|---|---|
| I001, F401, UP045, UP017, RUF010, RUF022, RUF100, F841 | `ruff check --fix` (safe fixes only) |
| E501 (53) | Wrap by hand: split strings, shorten comments. Don't change log text. |
| B904 (13) | `raise ... from exc` (or `from None` where the original is noise) |
| E712 (2, SQLAlchemy `== False`) | `.is_(False)`. Not `not x`, which would break the query. |
| SIM105, RUF059 | Fix by hand (`contextlib.suppress`, `_`-prefixed variable) |
| T201 in `asset_service/lifespans/kafka.py` | Replace `print` with `log.info` |

## Findings fixed with a behaviour change
| Rule | Location | Change |
|---|---|---|
| S105/S106 | `asset_service/settings.py` `s3_access_key`, `s3_secret_key` | Required fields with no default. Compose passes the existing RustFS app key (the one the workers use) through `${S3_ACCESS_KEY:-…}`. (Corrected during the build: compose's earlier `rustfsadmin`/`rustfspassword` was never a valid RustFS credential. RustFS ignores `RUSTFS_ROOT_*` and uses the image's `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`.) |
| S106 | `asset_service/s3/client.py` `get_s3_client` | Build the client from `settings` (endpoint, keys, region) instead of literals |
| S105 | `asset_service/api/s3_callbacks.py` `RUSTFS_SECRET_TOKEN` | New required `AssetSettings.rustfs_webhook_token` (env `RUSTFS_WEBHOOK_TOKEN`). Compose passes it. The compare logic stays as it is (R4). |
| S105 | `bff_token_handler/settings.py` `client_secret` | Required, with no default. `BffSettings` gets `secrets_dir="/run/secrets"`. Compose mounts the secret with `target: client_secret`. Remove the unused `CLIENT_SECRET_FILE` env. |
| T201 | the `main()` stubs in `__init__.py` of the three workers | Delete them, and `[project.scripts]` with them. Run `uv lock` in each worker. |
| S104 | the three worker `main.py` health servers | The host comes from `HEALTH_HOST`, default `"0.0.0.0"`, with `# noqa: S104` plus a comment saying a container needs it |

Tests: each affected service's root `tests/conftest.py` sets fake values for the new required env vars at import time, before `settings` is imported. The known-bug tests that pinned the old behaviour flip to the new behaviour, and lose `known_bug` where the bug is gone:
- `test_hardcoded_secret_is_accepted_with_any_scheme`: the secret now comes from settings. The any-scheme and `!=` parts stay `known_bug` for R4.
- `test_project_script_points_to_hello_world_stub` (email, cleanup): now asserts that there is no `[project.scripts]`.

## Non-goals
- The rest of R2: the DB URL, the worker S3 keys and bootstrap (`cleanup_buckets.main` dict literals, which S105 doesn't flag), and moving all secrets to files
- R4: `compare_digest`, the scheme check, the 403 on malformed headers, and the token in logs (R3)
- The rest of R12: dead code beyond the stubs, `get_s3_client_`, scratch files
- mypy (F6), pytest config and coverage (F7), CI and pre-commit (F8), pinning ruff in a lock file
- The frontend (Prettier already covers it)

## Roadmap and doc updates (done in this item)
- Tick F5. Add notes to R2 ("asset-service S3 keys, webhook token and BFF client secret done in F5"), R4 ("token already in settings") and R12 ("worker `main()` stubs removed in F5").
- `tech-stack.md` Tooling: "Lint/format: root `ruff.toml` (ruff ≥ 0.17.2, line length 88, rules …)". Remove "no config file".
- Add `.git-blame-ignore-revs` with the format-only commit.

## Acceptance criteria
1. From the repo root, `ruff check services` and `ruff format --check services` both exit 0. The same holds from inside each service directory.
2. `ruff check --show-settings services/asset-service/src` reports `/ruff.toml` as the settings path.
3. Every Python service passes `uv run --extra dev pytest` with no stack and no network. The test count only changes for flipped or removed tests that this spec names.
4. The format-only commit changes whitespace and layout only. The test suites pass before and after it, and its hash is in `.git-blame-ignore-revs`.
5. `grep -rn "OAhzGog\|5XItB3P\|your-secure-shared-secret\|dev-bff-client-secret" services/asset-service/src services/bff-token-handler/src` returns nothing. The worker S3 key literals (`cleanup_buckets/main.py`, `image_processor/main.py`, `main_no_preview.py`) are still there on purpose and are left for R2/R11 (see Non-goals). (Narrowed during the build: the first version grepped `services/*/src`, which contradicted the non-goals.)
6. Manual check on the stack: `make up`, then login works (the BFF secret comes from `/run/secrets/client_secret`), an upload reaches `OPTIMIZED` (S3 keys and webhook token), and the worker `/health` endpoints answer.
7. `uv lock` has been run in the three workers, and `docker compose build` succeeds.
