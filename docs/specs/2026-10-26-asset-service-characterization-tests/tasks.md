# Tasks: F1 asset-service characterization tests

Spec: [spec.md](spec.md)

- [x] 1. Spike: in a throwaway test, confirm that `Base.metadata.create_all` works on `sqlite+aiosqlite` with the postgres `UUID` columns, the `uuid.uuid7` defaults and `deleted == False` filters. Record any workaround in the spec. If sqlite cannot host the models, stop and come back to the decision.
- [x] 2. In `tests/conftest.py`, register the `known_bug` marker through `pytest_configure`. Check that `pytest --markers` lists it.
- [x] 3. Add `tests/api/conftest.py` with fixtures for:
  - the engine and session (StaticPool, `create_all` per test) and the `get_db` override
  - the `validate_dpop` no-op override
  - the fake Kafka producer on `app.state`
  - patched S3 presign and `get_s3_client`
  - an `httpx.AsyncClient`
  - seed helpers: `make_user`, `make_project` and `make_image(status=..., deleted=..., created_at=...)`

  Clear `dependency_overrides` on teardown. Prove the fixtures work with a `/health` test.
- [x] 4. `tests/api/test_identity.py`: missing, malformed and unknown `X-User-Sub`. A `known_bug` (R1) test shows that any caller can act as another user by setting their sub. Add the DPoP-wiring smoke test without the override.
- [x] 5. `tests/api/test_projects.py`: list (only the caller's, newest first), create (201, 422 shape), get (200/404/403).
- [x] 6. `tests/api/test_images_presign.py`:
  - Happy path: check the response, the DB row (key pattern, `raw_format`, PENDING status), the producer call and its event fields, and the presign key.
  - The `bin` fallback.
  - 422 cases: empty name, `/`, `\`, missing `fileSizeBytes`.
  - 403 for a foreign project, and a `known_bug` 403 for a missing project.
- [x] 7. `tests/api/test_images_list.py`:
  - The list excludes deleted images and orders newest first, with the schema fields.
  - Preview URL selection for each status: OPTIMIZED, PENDING, PROCESSING, FAILED.
  - 403 for a foreign project, and a `known_bug` 403 for a missing one.
- [x] 8. `tests/api/test_images_delete.py`:
  - 204 with `deleted=True` and `deleted_at` None (`known_bug`), plus the `ImageDeletedEvent` payload.
  - 404 for missing, already deleted and wrong-project images.
  - 500 on an unexpected service error (patch `ImageService.delete` to raise).
  - 403 for a foreign project, and a `known_bug` 403 for a missing one.
- [x] 9. `tests/api/test_rustfs_callback.py`:
  - ObjectCreated for a known key (event fields), for an unknown key, and with `%2F` decoding.
  - ObjectRemoved, both the first time and repeated.
  - Ignored event names, several records, a record with no key → 500, a wrong token → 403.
  - `known_bug` (R4) tests: missing header → 500, header with no space → 500, non-JSON body → 500, and any scheme is accepted.
- [x] 10. Run each test file on its own and then the full suite, to make sure no state leaks between tests. Run `pytest -m known_bug` and check that every row of the known-bugs table has a test.
- [x] 11. Check the acceptance criteria (no `src/` diff), then tick F1 in `docs/product/roadmap.md`.
