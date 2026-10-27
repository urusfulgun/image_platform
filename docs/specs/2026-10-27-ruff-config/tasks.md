# Tasks: F5 root ruff.toml

Spec: [spec.md](spec.md)

- [x] 1. Record the baseline: `ruff check --statistics services`, `ruff format --check services`, and the pytest pass count per service.
- [x] 2. Add `/ruff.toml` as specified. Check that `--show-settings` picks it up from the root and from a service directory, and that the finding counts match the baseline in the spec.
- [x] 3. Run `ruff format services`. Run every suite, then commit the format-only change: `style: apply ruff format`.
- [x] 4. Run `ruff check --fix services` (safe fixes only). Run every suite. Commit.
- [x] 5. Fix by hand: E501, B904, E712 (`.is_(False)`), SIM105, RUF059, and the lifespan `print` → `log.info`. Run every suite.
- [x] 6. asset-service secrets:
  - make the S3 key fields required
  - `get_s3_client` uses settings
  - add a `rustfs_webhook_token` setting, used in `s3_callbacks`
  - fake env in `tests/conftest.py`; `helpers.WEBHOOK_TOKEN` reads it
  - flip the R2 part of the any-scheme test
  - add `RUSTFS_WEBHOOK_TOKEN` to compose
- [x] 7. BFF secret:
  - make `client_secret` required, with `secrets_dir="/run/secrets"`
  - compose secret `target: client_secret`, and drop `CLIENT_SECRET_FILE`
  - fake env in `tests/conftest.py`
- [x] 8. Workers:
  - delete the `main()` stubs and `[project.scripts]`, then `uv lock`
  - flip the R12 stub tests
  - `HEALTH_HOST` env with a commented `noqa: S104`
- [x] 9. Run `ruff check services` and `ruff format --check services` (both clean), then every suite (green). Run the `grep` from acceptance criterion 5.
- [x] 10. Add `.git-blame-ignore-revs` with the task 3 commit. Update the roadmap (tick F5, add notes to R2/R4/R12) and `tech-stack.md`.
- [x] 11. Manual stack check: `docker compose up -d --build`, then login, an upload reaching `OPTIMIZED`, and the worker `/health` endpoints. (2026-10-27, a Playwright script as user `smoke-test` against `http://image-platform`. Login works, with an HttpOnly/Strict `sid` cookie, so the BFF secret comes from the file. `/me`, project creation, presign and the S3 PUT pass, so the S3 keys come from settings. Every `/health` returns 200. RustFS has no bucket notification configured, so the webhook was sent by hand: a wrong token gets 403, `RUSTFS_WEBHOOK_TOKEN` gets 200, and the image reached `OPTIMIZED` with an email in Mailpit. Fixed along the way: compose S3 keys (`97f34b3`) and F16.)
