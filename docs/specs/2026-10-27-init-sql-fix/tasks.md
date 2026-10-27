# Tasks: F16 init SQL fix

Spec: [spec.md](spec.md)

- [x] 1. Add the two missing commas in `01._init.sql`.
- [x] 2. Run the whole file on a scratch database (`createdb`, then `psql -v ON_ERROR_STOP=1 -f`, then `dropdb`) and check for four tables and the index.
- [x] 3. Record the `users`/`projects` row counts, apply sections 3 and 4 to the live `asset_metadata` database in one transaction, and recheck the counts and the new columns.
- [x] 4. Run the asset-service suite, then the F5 smoke test until the image reaches `OPTIMIZED`. (Presign and upload pass. RustFS has no bucket notification configured, so the webhook was sent by hand with the env token; the image then reached `OPTIMIZED` in 4 s.)
- [x] 5. Tick F16 in the roadmap, update `tech-stack.md` if needed, and commit.
