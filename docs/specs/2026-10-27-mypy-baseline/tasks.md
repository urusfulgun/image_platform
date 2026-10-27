# F6 tasks

- [ ] 1. Add `mypy>=2.4` to the `dev` extra of all six services and run `uv lock` and `uv sync --extra dev` in each.
- [ ] 2. Add `[tool.mypy]` and the overrides (aiokafka, tests) to each `pyproject.toml`. Get `uv run --extra dev mypy` running cleanly over `src` and `tests` (no duplicate `conftest`, `from helpers` resolves), adjusting `mypy_path`/`explicit_package_bases`. Record the final config choice in the spec.
- [ ] 3. Add `shared_core/py.typed`. Check that the shared_core `import-untyped` errors are gone in every dependent service.
- [ ] 4. Write `scripts/mypy_check.py`: normalise, multiset compare, report new and stale entries, `--update`, exit 2 on a mypy crash or early stop. It must pass ruff.
- [ ] 5. Generate `mypy-baseline.txt` in each service with `--update`. Read through it for anything that looks like a config mistake, not a real error. Record the counts in the spec.
- [ ] 6. Add a `make typecheck` target. Run it (exit 0).
- [ ] 7. Hand checks from acceptance criterion 5: inject an error, then remove a baselined error. Revert both.
- [ ] 8. Run every test suite, `ruff check services scripts` and `ruff format --check services scripts`.
- [ ] 9. Update the roadmap (tick F6), `tech-stack.md` (Type checking) and `CLAUDE.md` (Commands).
