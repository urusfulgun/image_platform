# F8: GitHub Actions CI

## Goal
Each PR and each push to `main` runs the checks that F5–F7 made available as commands: ruff lint and format, the mypy baseline check, and pytest with coverage floors in all six Python services, plus the frontend build, Vitest and Playwright. The workflow is one file, `.github/workflows/ci.yml`. It is read-only and has no secrets. Runtime code does not change.

## Today
- No `.github/` directory and no CI.
- Local commands it reuses: `ruff check .` / `ruff format --check .` (root `ruff.toml`, `required-version >=0.17.2`), `make typecheck` → `scripts/mypy_check.py`, `make test` → `pytest --cov`. Frontend: `bun install`, `bun run build`, `bun run test` (`@angular/build:unit-test`, Vitest), `bun run e2e` (Playwright, `webServer` starts `ng serve` on :4200, BFF mocked through `page.route`. When `CI` is set: `forbidOnly`, 2 retries, 1 worker, list + html reporters).
- Tests need no stack. Required settings get dummy values from conftests (`CLIENT_SECRET`, `S3_*`, `RUSTFS_WEBHOOK_TOKEN`).
- Versions: `.python-version` 3.14.2 in every service. The devcontainer uses 3.14.8 through `UV_PYTHON`. uv 0.13.5 locally, `packageManager: bun@1.3.9`, ruff 0.17.2.

## Workflow design (`.github/workflows/ci.yml`)
- **Triggers:** `pull_request`, `push` to `main`, and `workflow_dispatch`.
- **`permissions: contents: read`** at the top level. No secrets and no `pull_request_target`.
- **`concurrency`:** group `ci-${{ github.ref }}`, with `cancel-in-progress` set only for PR refs, so runs on main are never cancelled.
- **Pinning:** every `uses:` points at a full 40-character commit SHA with a `# vX.Y.Z` comment (checkout, setup-uv, setup-bun, upload-artifact). Tool versions are exact: uv `0.13.5` (setup-uv `version`), ruff `0.17.2`, Bun read from `packageManager` (`bun-version-file: services/frontend/package.json`).
- **`timeout-minutes`** on every job.
- **Job `ruff`** (runs once, because the config lives at the root): checkout, setup-uv, then `uvx ruff@0.17.2 check .` and `uvx ruff@0.17.2 format --check .` from the repo root. The roadmap says "matrix (ruff, …)". Running ruff once at the root checks the same files as running it per service, without six copies of the same job.
- **Job `python`** (matrix `service: [shared-core, asset-service, bff-token-handler, image-processor, email-notification, cleanup-buckets]`, `fail-fast: false`, `defaults.run.working-directory: services/${{ matrix.service }}`):
  1. checkout; setup-uv with `enable-cache` and `cache-dependency-glob: services/${{ matrix.service }}/uv.lock`
  2. `uv sync --locked --extra dev`. `--locked` fails when `uv.lock` is stale, which also catches the "forgot `uv lock`" Docker break from CLAUDE.md.
  3. `uv run --extra dev python ../../scripts/mypy_check.py`
  4. `uv run --extra dev pytest --cov`
  - Python comes from `.python-version` (3.14.2), the version the Dockerfiles use, and uv installs it. The devcontainer's 3.14.8 is not copied in. Aligning the versions is F12.
- **Job `frontend`** (`working-directory: services/frontend`): checkout, setup-bun, `bun install --frozen-lockfile`, `bun run build`, `bun run test --watch=false`. (Decided during the build: `bun run` passes trailing flags to the script without a `--` separator, so the spec's `-- --watch=false` became `--watch=false`.)
- **Job `e2e`** (`working-directory: services/frontend`): checkout, setup-bun, `bun install --frozen-lockfile`, `bunx playwright install --with-deps chromium firefox`, `bun run e2e`. GitHub sets `CI=true`, so the existing CI branch of `playwright.config.ts` applies without changes. If the job fails, `playwright-report/` and `test-results/` are uploaded as an artifact with 7-day retention. It is a separate job so that a slow browser install doesn't hold up the build/Vitest result.
- Jobs run in parallel with no `needs:`.
- Added during the build: `persist-credentials: false` on every checkout, so the `GITHUB_TOKEN` isn't left in `.git/config` for later steps. Runners are pinned to `ubuntu-24.04` rather than `ubuntu-latest`. The `ruff` job sets `enable-cache: false` because the root has no `uv.lock` to key a cache on.

## Local run (2026-10-27)
- `actionlint` 1.7.12 (`uvx --from actionlint-py actionlint`): no findings.
- `ruff check .` and `ruff format --check .` from the root: clean.
- Python legs, run as in CI: `UV_PYTHON` unset so `.python-version` applies (3.14.2), with `uv sync --locked --extra dev` into a scratch venv per service. Every lock is current, every mypy baseline matches on 3.14.2 (the same 170 entries as on the devcontainer's 3.14.8), and every suite passes at or above its floor.
- Frontend: `bun install --frozen-lockfile`, `bun run build`, `bun run test --watch=false` (4 tests) and `CI=true bun run e2e` (14 tests, Chromium and Firefox) all pass.

## Action pins
Latest release of each action on 2026-10-27, resolved to its commit with `git ls-remote` (peeled for annotated tags):

| Action | Version | SHA |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `astral-sh/setup-uv` | v10.3.2 | `07a047e608db84b3d8c06cd9a7c7dcc9c355c18e` |
| `oven-sh/setup-bun` | v2.2.0 | `0c5077e51419868618aeaa5fe8019c62421857d6` |
| `actions/upload-artifact` | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

All four run on `node24`. The inputs the workflow uses (`version`, `enable-cache`, `cache-dependency-glob`, `bun-version-file`, `retention-days`, `if-no-files-found`) were checked against each pinned `action.yml`.

## CI runs (2026-10-27)
- **First run** on PR head `b0be894` (run 40518533980): all 9 jobs passed. The mypy baselines match on 3.14.2 in CI too, so acceptance criterion 7 needed no change.
- **Hand check** with `d214b2d`, which adds `tests/test_ci_hand_check.py` to email-notification with `assert 1 == 2` (run 40519455158): only `python (email-notification)` failed, and the other 8 jobs passed. That confirms `fail-fast: false`. The leg failed at its **mypy** step, not at pytest: strict mode reports `Non-overlapping equality check [comparison-overlap]` on the literal comparison, so the pytest step was skipped. Locally the same file fails both the mypy check and pytest. As built, a leg stops at its first failing check, so a PR that breaks both types and tests only shows the mypy failure until it is fixed.
- **Revert** `9ff2d29` (`git revert` of `d214b2d`, run 40519791913): 8 jobs passed. `python (image-processor)` stayed queued with no runner and no steps, yet GitHub reported the run as `completed / success`. So the run's conclusion alone doesn't prove every job passed; check each job.
- **Closing docs commit** (`docs: close F8 GitHub Actions CI`): its run is the first one after the revert in which all 9 jobs ran. The result is recorded below.
- Branch protection: the owner set it up by hand after the green run. A `main` ruleset (no bypass list) requires a PR with 0 approvals, requires all 9 checks from GitHub Actions with the branch up to date, and blocks force pushes and deletion. The PR now lists the checks as required. The check names are the job names, so renaming a job or changing the matrix also means editing the ruleset.

## Non-goals
- pip-audit, Trivy, CodeQL or other scanning (F11). Dependabot or Renovate for actions, locks and images (F10).
- Building or pushing Docker images. Running the compose stack or a smoke test (F17).
- Coverage upload, badges or README changes (N8).
- Branch protection or required checks. These are GitHub repo settings, not code. After the first green run, the owner should mark the jobs as required checks on `main` by hand.
- Prettier or ESLint checks for the frontend (no script exists). Caching Playwright browsers.
- Changing Python to 3.14.8 (F12), or changing `playwright.config.ts`, `Makefile` or any service code.

## Roadmap and doc updates (done in this item)
- Tick F8 in `roadmap.md`.
- `tech-stack.md`: **CI** changes to describe the workflow (jobs, triggers, SHA pinning, tool versions). Remove "Not enforced yet (F8)" from Lint/format, Type checking and Tests. In Target Tooling, mark CI as done or trim it to what remains (gating Dependabot PRs is F10).
- `CLAUDE.md`: a short "CI" line under Commands with `.github/workflows/ci.yml`, what it runs, and the fact that `uv sync --locked` fails on a stale `uv.lock`.

## Acceptance criteria
1. `.github/workflows/ci.yml` exists with the triggers, `permissions: contents: read`, concurrency and the four jobs (`ruff`, `python` ×6, `frontend`, `e2e`) described above.
2. Every `uses:` is a 40-hex SHA with a version comment. uv, ruff and Bun versions are exact.
3. `actionlint` reports no errors for the workflow.
4. Locally, each job's commands pass from its working directory. Locally this already means `ruff check .`, `ruff format --check .`, `make typecheck`, `make test`, `bun run build`, `bun run test --watch=false` and `bun run e2e`.
5. On GitHub, the workflow runs on a PR from this branch, and every job is green, including all six matrix legs and both Playwright browsers.
6. Hand check on a scratch commit in that PR (reverted before merge): a new mypy error or a failing test turns the matching matrix leg red while the other legs stay green, which confirms `fail-fast: false`.
7. If the mypy baseline differs on 3.14.2 in CI compared with the devcontainer, the difference is recorded here with how it was resolved.
8. The roadmap, `tech-stack.md` and `CLAUDE.md` are updated as listed.
