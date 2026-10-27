# F6: `mypy --strict` config per service, with a baseline

## Goal
Every Python service gets a locked mypy version and a `[tool.mypy]` config: `--strict` for `src`, relaxed for `tests`. Today's errors are recorded in a committed baseline. One command per service passes on today's tree and fails on any new error. F8 can then gate on it, and later items can shrink the baseline. Runtime behaviour does not change.

Measured on 2026-10-27 with mypy 2.4.0 `--strict` on `src`, before this item:

| Service | src errors | Main codes |
|---|---|---|
| shared-core | 10 | arg-type, no-untyped-def |
| asset-service | 87 | no-untyped-def 34, import-untyped 22 |
| bff-token-handler | 41 | import-untyped 14, no-untyped-def 9, type-arg 8 |
| image-processor | 27 | no-untyped-def 9, import-untyped 6 |
| email-notification | 8 | |
| cleanup-buckets | 11 | |

Most `import-untyped` errors happen because shared-core ships no `py.typed`. The rest come from `aiokafka`, which ships no types. Running mypy on `src tests` stops on `Duplicate module named "conftest"` in shared-core, asset-service and bff-token-handler. Their tests use `from helpers import …`, which only resolves through pytest's sys.path insertion.

## Config (each service's `pyproject.toml`)
- `mypy>=2.4` in the `dev` extra, then `uv lock`. Run it as `uv run --extra dev mypy` so it sees the service venv.
- `[tool.mypy]`:
  - `strict = true`, `python_version = "3.14"`, `warn_unused_configs = true`
  - `files = ["src", "tests"]`
  - `plugins = ["pydantic.mypy"]`, so required `BaseSettings` fields are typed correctly
  - `explicit_package_bases = true`, `mypy_path = ["src"]`
  - Decided during the build: putting `tests/api` on `mypy_path` made `from helpers import …` resolve, but it turned those files into top-level modules (`test_health`, `helpers`). mypy override patterns accept only exact names or a `pkg.*` suffix, so the relaxed `tests.*` override couldn't reach them. Instead, `tests/` and `tests/api` (asset-service, bff-token-handler) or `tests/endpoint` (shared-core) became packages with an `__init__.py`. Their imports changed to `from tests.api.helpers import …` / `from tests.endpoint.helpers import …`, the style that email-notification and cleanup-buckets already use. No test files moved.
- `[[tool.mypy.overrides]]` for `aiokafka`: `ignore_missing_imports = true`. It ships no types and has no stubs package. It's only in the four services that import it, because `warn_unused_configs` flags unused sections.
- `[[tool.mypy.overrides]]` for `tests.*`:
  - set `disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_calls` and `disallow_untyped_decorators` to `false`
  - keep `check_untyped_defs = true`
- No root `mypy.ini`. The config is per service, as the roadmap says, because each service has its own venv.

## Code change
- Add an empty `services/shared-core/src/shared_core/py.typed`. This clears the false `import-untyped` errors in the five dependent services. `uv_build` includes it automatically.

## Baseline
- Each service commits `mypy-baseline.txt`: mypy's error lines, normalised to `path: error: message  [code]`. Line and column numbers are dropped, so editing nearby code doesn't churn the file. Lines are sorted, duplicates are kept, and notes are left out.
- `scripts/mypy_check.py` (stdlib only), run from a service directory:
  - `uv run --extra dev python ../../scripts/mypy_check.py` runs mypy and normalises the output. It compares the result with the baseline as a multiset.
  - It exits 1 and prints the new errors (with line numbers) if any error is not in the baseline.
  - It exits 1 and lists stale entries if any baseline entry no longer occurs. This is a ratchet: the baseline can only shrink. The message says to run `--update`.
  - `--update` rewrites the baseline.
  - It exits 2 if mypy crashes or stops early (for example a duplicate-module error), so an empty result can't pass by accident.
- `make typecheck` runs the check in every service and exits non-zero if any of them fails.

Baseline counts at the end of F6, covering `src` and `tests` after `py.typed` and the aiokafka override:

| Service | Entries | Main codes |
|---|---|---|
| shared-core | 15 | type-arg 6, no-untyped-def 4, arg-type 4 |
| asset-service | 76 | no-untyped-def 34, arg-type 12, no-any-return 8 |
| bff-token-handler | 37 | type-arg 10, no-untyped-def 9, arg-type 7 |
| image-processor | 24 | no-untyped-def 9, type-arg 5, no-untyped-call 4 |
| email-notification | 7 | no-untyped-def 4 |
| cleanup-buckets | 11 | no-untyped-def 5 |
| **Total** | **170** | |

A read-through of the baselines found no config mistakes. Two entries are real bugs that were left for later items:
- `bff_token_handler/session/redis_store.py`: `redis_key_tag` reads `Template.args`, which doesn't exist in Python 3.14's `string.templatelib` (it was in a PEP 750 draft). Only commented-out code calls it, so it is dead code (R12).
- `image_processor/main_no_preview.py` builds `ImageAvifReadyEvent` without the required `preview_s3_path` and `processed_format` (dead code, R12).

## Non-goals
- Fixing type errors other than `py.typed` (later items shrink the baseline)
- CI wiring (F8), pre-commit hooks, the frontend
- Stubs for `aiokafka`, mypy plugins beyond pydantic, `pytest-cov` (F7)

## Roadmap and doc updates (done in this item)
- Tick F6.
- `tech-stack.md` Tooling, "Type checking": mypy 2.4.x, locked in each `dev` extra, `[tool.mypy]` strict for src and relaxed for tests, a per-service `mypy-baseline.txt` with its entry counts, `make typecheck`, not enforced yet (F8).
- `CLAUDE.md` Commands: replace `mypy --strict src` with the `mypy_check.py` command, `--update`, and `make typecheck`.

## Acceptance criteria
1. Each of the six services has `mypy` in `dev` (locked in `uv.lock`) and a `[tool.mypy]` matching this spec.
2. `uv run --extra dev mypy` in each service runs over `src` and `tests` with no duplicate-module or config error (type errors only).
3. `services/shared-core/src/shared_core/py.typed` exists, and no baseline contains an `import-untyped` entry for `shared_core` or `aiokafka`.
4. `make typecheck` exits 0 on the committed tree.
5. Adding a deliberate type error to any service's `src` makes that service's check exit 1 and print the new error. Removing an error without `--update` exits 1 and reports a stale entry. Both are checked by hand and then reverted.
6. Every test suite still passes. `ruff check services` and `ruff format --check services` stay clean, and so does `ruff check scripts`.
7. The spec records the per-service baseline counts.
