# F7: Pytest config and `pytest-cov` in every service

## Goal
Every Python service gets a `[tool.pytest.ini_options]` and a `[tool.coverage.*]` config in its `pyproject.toml`, with `pytest-cov` locked in its `dev` extra. Coverage is measured per service, and a `fail_under` floor taken from today's numbers stops it dropping. `make test` runs every suite with coverage and fails if any suite fails or falls below its floor. F8 can then gate on one command. Runtime behaviour does not change.

The Vitest half of F7 is already done: `services/frontend/src/app/app.spec.ts` was fixed and passes (commit 3eb6d53). This spec covers only the Python services.

## Today
- No service has pytest or coverage config. Tests run with pytest's defaults from the service directory.
- `known_bug` is registered by the same `pytest_configure` hook in five conftests (shared-core, asset-service, bff-token-handler, email-notification, cleanup-buckets). A typo in a marker name would pass silently.
- image-processor has no conftest and no `tests/__init__.py`.
- Markers in use: `asyncio`, `known_bug`, `parametrize`. No `xfail`.
- `.gitignore` already ignores `.coverage*`, `htmlcov/` and `coverage.xml`.

## Config (each service's `pyproject.toml`)
- `pytest-cov>=7.1.0` in the `dev` extra (the latest release at build time, `>=` only like the rest), then `uv lock`. It brings in coverage 7.17.0; no other locked version changed.
- `[tool.pytest.ini_options]`:
  - `minversion = "9.0"`
  - `testpaths = ["tests"]`
  - `addopts = ["-ra"]`
  - `strict_markers = true`, `strict_config = true`
  - `xfail_strict = true`
  - Decided during the build: the spec first put `--strict-markers --strict-config` in `addopts`. pytest 9 made those flags overrides of the new `strict_markers` / `strict_config` ini options, and they have no effect when given through `addopts` (pytest 9.0.2): a misspelt `@pytest.mark.knwon_bug` only warned. The ini keys work, so they replace the flags. pytest 9's umbrella `strict = true` was not used, because it would also turn on any strictness options added in later pytest releases.
  - `markers = ["known_bug: characterization test pinning current buggy behaviour; the comment names the roadmap item that changes it"]`. Only in services that use it, so image-processor doesn't carry an unused entry. (`--strict-markers` would reject it anyway if missing.)
  - No `asyncio_mode`: tests keep marking `@pytest.mark.asyncio` explicitly, as CLAUDE.md says.
  - No `filterwarnings` change.
- Coverage is **not** in `addopts`. Otherwise running a single test (`pytest tests/x.py::test_y`) would fail the `fail_under` check. Coverage runs when `--cov` is passed, which `make test` and F8 do.
- `[tool.coverage.run]`: `source = ["<package>"]` (the service's own package under `src`, e.g. `asset_service`; shared-core counts only in its own suite), `branch = true`.
- `[tool.coverage.report]`: `show_missing = true`, `skip_covered = true`, `fail_under = <floor>`, `exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError", "if __name__ == .__main__.:"]`.
- Run as `uv run --extra dev pytest --cov`. With no argument, `--cov` takes `source` from the coverage config.

## Code change
- Delete the `pytest_configure` hook from the five conftests (and any import it alone needed). Nothing else in the conftests changes.

## Coverage floors
Measured with `--cov` and branch coverage on the tree at the start of this item. The floor is the measured total rounded **down** to a whole percent, so a small refactor doesn't flip it. Recorded here during the build:

| Service | Measured | `fail_under` |
|---|---|---|
| shared-core | 64.84% | 64 |
| asset-service | 79.51% | 79 |
| bff-token-handler | 82.51% | 82 |
| image-processor | 38.60% | 38 |
| email-notification | 71.11% | 71 |
| cleanup-buckets | 77.50% | 77 |

Measured on 2026-10-27 with pytest-cov 7.1.0 (coverage 7.17.0). Because `source` names the package, modules that no test imports are counted at 0% instead of being left out. That is most of the gap in shared-core (the security schemas, `key_pair_marshalling`, `s3_object_key`) and image-processor (the dead `main_no_preview.py`, R12). The worker totals are lower mainly because the `run()` / `__main__` startup code is untested.

Raising a floor is a manual edit, done when tests are added (like `mypy_check.py --update`, but by hand). This item adds no tests to raise numbers.

## `make test`
A target modelled on `make typecheck`: for each of `PYTHON_SERVICES`, `cd services/$s && uv run --quiet --extra dev pytest --cov`. It runs every service even after a failure and exits non-zero if any failed.

## Non-goals
- New tests or higher coverage (later items add tests; floors get raised then)
- CI wiring and coverage upload or badges (F8)
- `filterwarnings = error`, `asyncio_mode = auto`, parallel runs (`pytest-xdist`)
- The frontend (its Vitest spec is already fixed) and frontend coverage
- Moving to pytest 9's native `[tool.pytest]` table. The roadmap and tech-stack name `[tool.pytest.ini_options]`, which pytest 9 still supports.

## Roadmap and doc updates (done in this item)
- Tick F7, removing the "still open" note.
- `tech-stack.md` Tooling, "Tests": pytest-cov version, `[tool.pytest.ini_options]` with strict markers and config, branch coverage, per-service floors, `make test`, not enforced yet (F8). Target "Tests" bullet: drop the config/pytest-cov part as done.
- `CLAUDE.md` Commands: add `uv run --extra dev pytest --cov` and `make test`. Note that `known_bug` is registered in `pyproject.toml`.
- `.claude/commands/test.md`: no change needed (it runs plain `pytest`); mention `--cov` passes through as an argument only if it reads naturally.

## Acceptance criteria
1. Each of the six services has `pytest-cov` in `dev` (locked in `uv.lock`), plus `[tool.pytest.ini_options]` and `[tool.coverage.run]`/`[tool.coverage.report]` matching this spec.
2. No conftest defines `pytest_configure` to register `known_bug`; `grep -rn pytest_configure services/*/tests` is empty.
3. `uv run --extra dev pytest` in each service passes, with no coverage output and no `fail_under` check.
4. `uv run --extra dev pytest --cov` in each service passes, prints a branch-coverage report for that service's package only, and meets its floor.
5. `make test` exits 0 on the committed tree.
6. Hand checks, then reverted: a test marked `@pytest.mark.knwon_bug` fails collection; raising one floor above its measured value makes `make test` exit non-zero; a single-test run (`pytest tests/<file>::<test>`) still passes.
7. `make typecheck` still exits 0 (the conftest edits don't add or remove baseline entries, or the baseline is updated and the reason recorded). `ruff check services` and `ruff format --check services` stay clean.
8. The spec records the measured coverage and the floor per service.
