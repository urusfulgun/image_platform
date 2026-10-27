# F7 tasks

- [x] 1. Add `pytest-cov` to the `dev` extra of all six services and run `uv lock` and `uv sync --extra dev` in each.
- [x] 2. Add `[tool.pytest.ini_options]` to each `pyproject.toml` (`minversion`, `testpaths`, `addopts = ["-ra"]`, `strict_markers`, `strict_config`, `xfail_strict`, and the `known_bug` marker where used). Run `uv run --extra dev pytest` in each; all pass.
- [x] 3. Remove the `pytest_configure` hooks from the five conftests. Re-run each suite; all pass and no unknown-marker error.
- [x] 4. Add `[tool.coverage.run]` (`source`, `branch`) and `[tool.coverage.report]` (`show_missing`, `skip_covered`, `exclude_also`) without `fail_under`. Run `pytest --cov` in each service and check the report covers only that service's package.
- [x] 5. Record the measured totals in the spec table, set `fail_under` to each total rounded down, and re-run `pytest --cov` (all pass).
- [x] 6. Add the `make test` target. Run it (exit 0).
- [x] 7. Hand checks from acceptance criterion 6: misspelt marker, floor raised too high, single-test run. Revert.
- [x] 8. Run `make typecheck`, `ruff check services` and `ruff format --check services`. Update a mypy baseline only if the conftest edits changed it, and note why in the spec.
- [x] 9. Update the roadmap (tick F7), `tech-stack.md` (Tests, current and target) and `CLAUDE.md` (Commands).
