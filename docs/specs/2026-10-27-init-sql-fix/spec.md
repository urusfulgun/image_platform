# F16: Fix the init SQL (missing commas) so a fresh install works

## Goal
`init-db/postgres-image-metadata/01._init.sql` runs without errors on a fresh Postgres volume, so `image_metadata` and `image_processing_status` exist. The running dev database, which was initialised with the broken file, gets the missing tables without a volume wipe.

Found during the F5 smoke test: on first init (2026-10-26), Postgres logged `syntax error at or near "deleted_at"` at line 33 and stopped. Only `users` and `projects` were created, so every presign failed with `relation "image_metadata" does not exist`.

## Scope
- Add the two missing commas in `CREATE TABLE image_metadata` (after `created_at` and after `deleted_at`).
- Apply sections 3 and 4 of the file (the two tables, the index and the `ALTER ... IF NOT EXISTS` columns) to the running `asset_metadata` database in one transaction.

## Non-goals
- No other schema change. The drift between the SQL and `db/models.py` (for example, `raw_format` is nullable in SQL but `nullable=False` in the model) is left for R10.
- No Alembic (R10). No volume wipe.
- No change to `users` or `projects`, or to their data.

## Acceptance criteria
1. On a scratch database, the whole fixed file runs with `psql -v ON_ERROR_STOP=1` and creates all four tables plus `idx_status_lookup`.
2. The running `asset_metadata` database has `image_metadata` (including `preview_s3_path`, `deleted_at` and `deleted`) and `image_processing_status`. Existing rows in `users` and `projects` are unchanged.
3. The asset-service suite still passes.
4. The F5 smoke test reaches presign, and an uploaded image reaches `OPTIMIZED`.
