# F8 tasks

- [ ] 1. Look up the current release and full commit SHA of `actions/checkout`, `astral-sh/setup-uv`, `oven-sh/setup-bun` and `actions/upload-artifact`, and record them in the spec's "Action pins" table.
- [ ] 2. Write `.github/workflows/ci.yml`: triggers, permissions, concurrency, and the `ruff` job.
- [ ] 3. Add the `python` matrix job (`uv sync --locked --extra dev`, mypy check, `pytest --cov`).
- [ ] 4. Add the `frontend` job (install, build, Vitest with `--watch=false`) and confirm `bun run test -- --watch=false` exits locally.
- [ ] 5. Add the `e2e` job (browser install, `bun run e2e`, upload the report on failure).
- [ ] 6. Run `actionlint` (for example `uvx --from actionlint-py actionlint`) and fix any findings.
- [ ] 7. Run every job's commands locally (acceptance criterion 4).
- [ ] 8. Ask before pushing. Then push the branch, open a draft PR and get every job green, fixing anything that only fails in CI (for example a mypy baseline difference on 3.14.2) and recording it in the spec.
- [ ] 9. Hand check: push a scratch commit that breaks one service, check that only its leg fails, then revert it.
- [ ] 10. Update the roadmap (tick F8), `tech-stack.md` (CI, the "Not enforced yet" notes, Target) and `CLAUDE.md` (CI line). Note branch protection as a manual follow-up.
