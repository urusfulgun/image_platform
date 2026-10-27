# F1: Characterization tests for the asset-service API

## Goal
Pin the current HTTP behaviour of asset-service's project, image and RustFS callback routes with tests that need no running stack. Later refactors (R1, R4, R9, R10, R13) can then be checked against them. Tests describe what the code **does**, not what it should do.

## Scope
Routes, exercised through the real FastAPI `app` (`asset_service.main`) with `httpx.AsyncClient` + `ASGITransport(raise_app_exceptions=False)`. The lifespan does not run.
- `GET /projects/`, `POST /projects/`, `GET /projects/{id}`
- `GET /projects/{id}/images/`, `GET /projects/{id}/images/preview`
- `POST /projects/{id}/images/presign`
- `DELETE /projects/{id}/images/{image_id}`
- `POST /callback/rustfs`
- Identity resolution in `api/deps.py` (`X-User-Sub` → `UserModel`)
- One smoke test showing that `validate_dpop` is wired: with no override, a request without DPoP headers gets 401 "Missing Security Headers"

Test harness:
- Real `ProjectService`/`ImageService` on SQLAlchemy with `sqlite+aiosqlite://` (`StaticPool`), with tables built from `Base.metadata.create_all`. `get_db` is overridden.
- `app.state.kafka_producer` is an `AsyncMock(spec=AssetKafkaProducer)`.
- `generate_upload_presigned_url` is patched where `asset_service.api.images` uses it, and `get_s3_client` is patched in `asset_service.domain.images`. Both return deterministic fake URLs.
- `validate_dpop` is replaced via `app.dependency_overrides` with a no-op.
- The `known_bug` marker is registered in `tests/conftest.py` through `pytest_configure`. The pytest config file itself belongs to F7.

## Non-goals
- No changes under `src/`. Bugs are pinned, not fixed.
- No tests of `rs_dpop` internals (F3), Kafka consumers or lifespans.
- No pytest `ini_options`, coverage or CI (F7, F8).
- No Postgres or Testcontainers. Postgres-only behaviour (tz-aware timestamps, constraints from the init SQL) is out of scope.
- No new dependencies. `aiosqlite`, `httpx` and `pytest-mock` are already in the `dev` extra.

## Behaviour to pin
| Area | Behaviour |
|---|---|
| Identity | No `X-User-Sub` → 401 "Missing user identity". A non-UUID value → 401 "Invalid user identity format". An unknown sub → 404 "User not synced yet". |
| Projects | List returns only the caller's projects, newest first. Create returns 201 with `ProjectSchema`, and a missing `name` gives 422 `{detail, body}`. Get returns 200 to the owner, 404 when the project is missing and 403 when someone else owns it. |
| Presign | Returns 201 `{image_id, upload_url}`. The body uses the `fileName`/`fileSizeBytes` aliases. A missing `fileSizeBytes` or snake_case keys give 422. A `fileName` that is blank or contains `/` or `\` is rejected with 500 (see known bugs). The row stores `raw_s3_path = {project_id}/{uuid}/normal.{ext}` with `ext` set to `bin` when there is no suffix, and `raw_format = ext`, with status `PENDING`. The request publishes an `ImageRawUploadedEvent` via `publish_image_raw_presign_link_generated_topic` and asks for a presigned URL for the same key. |
| Delete | Returns 204. It sets `deleted=True` and leaves `deleted_at` as None. It publishes an `ImageDeletedEvent` with the raw, processed and preview paths. An image that is missing, already deleted or in another project gives 404. An unexpected service error gives 500 "Internal server error during deletion". |
| List / preview | Deleted images are excluded and the newest comes first. Preview: `OPTIMIZED` takes `display_url` from `processed-images` + `preview_s3_path`, and `processed_image_url` from `processed_s3_path`. `PENDING` uses the raw display URL and sets `processed_image_url = None`. `PROCESSING`/`FAILED` use the raw display URL and set `raw_image_url = None`. |
| Callback | A valid token is any `<scheme> your-secure-shared-secret`. `eventName` matches on the substring `ObjectCreated` → `publish_image_raw_uploaded` for the known key, and the key has `%2F` decoded. An unknown key gives 200 with nothing published. `ObjectRemoved` on an image with `deleted_at=None` sets `deleted=True` and `deleted_at`, and a second time is a no-op. Other events are ignored. Several records are handled in order. The response is `{"status": "success"}`. A wrong token gives 403. A record with no `s3.object.key` gives 500 "Internal processing error". |

## Known bugs pinned
Each of these tests gets `@pytest.mark.known_bug` and a `# CHARACTERIZATION: changes in <ID>` comment. The refactor that fixes a bug flips its assertion on purpose.

| Behaviour | Fixed by |
|---|---|
| `X-User-Sub` is trusted from any caller with no tie to the token's `sub` | R1 |
| Image routes map "project not found" to 403, not 404 (list, preview, presign, delete) | R1 or later API cleanup |
| Callback with no `Authorization` header gives 500, not 403 | R4 |
| Callback with `Authorization` that has no space gives 500 | R4 |
| Callback with a non-JSON body gives 500 (the JSON is parsed inside the auth dependency) | R4 |
| The webhook secret is hardcoded and compared with `!=` | R2 / R4 |
| Presign publishes the event before any upload, on the `uploading_link_generated` topic | R15 |
| API delete never sets `deleted_at` (only the callback's `delete_confirm` does) | R10 or later |
| A `fileName` that fails the `PresignRequest` validator gives 500, not 422. `main.py`'s validation handler echoes `exc.errors()`, whose `ctx` holds a raw `ValueError` that `JSONResponse` can't serialize. *Found during the build.* | No roadmap item yet |

## Build notes
- Task 1 spike: SQLite with `sqlite+aiosqlite` + `StaticPool` hosts the models as they are (postgres `UUID`, `uuid.uuid7` defaults, `deleted == False` filters, `selectinload`). No workaround was needed.

## Acceptance criteria
1. `cd services/asset-service && uv run --extra dev pytest` passes with no Docker stack and no network access.
2. Every route listed in Scope has at least one success test and one failure test.
3. Every row in "Behaviour to pin" and "Known bugs pinned" has at least one matching test. Each known-bug test has the `known_bug` marker and names its roadmap ID in a comment.
4. `pytest -m known_bug` selects only the known-bug tests, and no unknown-marker warning appears.
5. `git diff --stat` shows changes only under `services/asset-service/tests/`, this spec folder and the roadmap checkbox.
6. The existing `tests/test_user_sync_handler.py` still passes unchanged.
