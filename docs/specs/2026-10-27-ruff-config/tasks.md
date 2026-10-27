# Tasks: F5 root ruff.toml

Spec: [spec.md](spec.md)

- [ ] 1. Record the baseline: `ruff check --statistics services`, `ruff format --check services`, and the pytest pass count per service.
- [ ] 2. Add `/ruff.toml` as specified. Check that `--show-settings` picks it up from the root and from a service directory, and that the finding counts match the baseline in the spec.
- [ ] 3. Run `ruff format services`. Run every suite, then commit the format-only change: `style: apply ruff format`.
- [ ] 4. Run `ruff check --fix services` (safe fixes only). Run every suite. Commit.
- [ ] 5. Fix by hand: E501, B904, E712 (`.is_(False)`), SIM105, RUF059, and the lifespan `print` → `log.info`. Run every suite.
- [ ] 6. asset-service secrets:
  - make the S3 key fields required
  - `get_s3_client` uses settings
  - add a `rustfs_webhook_token` setting, used in `s3_callbacks`
  - fake env in `tests/conftest.py`; `helpers.WEBHOOK_TOKEN` reads it
  - flip the R2 part of the any-scheme test
  - add `RUSTFS_WEBHOOK_TOKEN` to compose
- [ ] 7. BFF secret:
  - make `client_secret` required, with `secrets_dir="/run/secrets"`
  - compose secret `target: client_secret`, and drop `CLIENT_SECRET_FILE`
  - fake env in `tests/conftest.py`
- [ ] 8. Workers:
  - delete the `main()` stubs and `[project.scripts]`, then `uv lock`
  - flip the R12 stub tests
  - `HEALTH_HOST` env with a commented `noqa: S104`
- [ ] 9. Run `ruff check services` and `ruff format --check services` (both clean), then every suite (green). Run the `grep` from acceptance criterion 5.
- [ ] 10. Add `.git-blame-ignore-revs` with the task 3 commit. Update the roadmap (tick F5, add notes to R2/R4/R12) and `tech-stack.md`.
- [ ] 11. Manual stack check: `docker compose up -d --build`, then login, an upload reaching `OPTIMIZED`, and the worker `/health` endpoints.
