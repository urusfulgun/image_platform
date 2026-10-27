# F4: First tests for the email-notification and cleanup-buckets workers

## Goal
Pin what `email_notification.main` and `cleanup_buckets.main` do today, with tests that need no Kafka, S3 or SMTP, so that R2, R11, R12, R14, R15, R19 and N4 can be checked against them. Tests describe what the code **does**, not what it should do.

## Scope
Code under test:
- `services/email-notification/src/email_notification/main.py`: `NotificationWorker` (`run`, `send_notification`), `/health`, `main()`
- `services/cleanup-buckets/src/cleanup_buckets/main.py`: `KafkaCleanupWorker` (`run`, `handle_cleanup`, `send_to_dlq`), `/health`, `main()`

Test harness (per service, `tests/`):
- `tests/conftest.py` registers the `known_bug` marker through `pytest_configure`, with the same wording as asset-service.
- A `FakeConsumer` (and, for cleanup, a `FakeProducer`) patched over `<module>.AIOKafkaConsumer` / `AIOKafkaProducer`. It does the following:
  - records the constructor args and kwargs, so tests can reach the real `value_deserializer` / `value_serializer` lambdas
  - async-iterates a given list of `SimpleNamespace(value=...)` messages
  - exposes `start`, `stop`, `commit` and `send_and_wait` as `AsyncMock`s, with a call log that records their order

  This also means no running event loop is needed at construction.
- email: `aiosmtplib.send` is patched at `email_notification.main.send` (an `AsyncMock`), and the test inspects the `EmailMessage` it receives.
- cleanup: `worker.session` is replaced with a stub whose `client("s3", **cfg)` returns an async context manager yielding an `AsyncMock` S3 client. The stub records `cfg`, and `delete_object` can be set to raise per key.
- `/health`: `httpx.AsyncClient(transport=ASGITransport(app))`, with `<module>.worker_instance` monkeypatched.
- `main()`: patch the worker class with a `MagicMock` whose side effect records its kwargs and raises a sentinel exception, so `main()` stops before the TaskGroup. Assert on the kwargs. Use `monkeypatch.setenv`/`delenv` for env vars.
- Event payloads are built from the real `shared_core.events.kafka_events` models (`ImageAvifReadyEvent`, `ImageDeletedEvent`) and dumped with `model_dump(mode="json")`.

## Non-goals
- No changes under `src/` and no bug fixes.
- No real Kafka, S3 or SMTP, and no testcontainers or moto. No new dependencies: pytest, pytest-asyncio, pytest-mock and httpx are already in the `dev` extra, so `uv.lock` stays unchanged.
- The TaskGroup/signal shutdown in `main()` isn't tested.
- No image-processor tests. That service isn't part of F4.
- No pytest `ini_options`, coverage or CI (F7, F8).

## Behaviour to pin: email-notification
| Area | Behaviour |
|---|---|
| Consumer config | It subscribes to `image.avif.ready` with group `notification-group`, `enable_auto_commit=False` and the given bootstrap server. The deserializer turns JSON bytes into a dict. |
| Message | `From` is the configured sender. `To` is `developer@example.local`. `Subject` is `✨ Image Processed: <image_id>`. The body contains the image ID, project ID, `processed_s3_path` and `http://localhost/upload/<project_id>`. |
| SMTP call | `send(msg, hostname=smtp_host, port=smtp_port, use_tls=False)`, called once per event. |
| Run loop | `start` comes first. A valid event is sent, then committed. `stop` runs when the iterator ends. |
| Invalid payload | A dict that doesn't validate (for example a missing `project_id`) logs an error with the `image_id`, sends nothing, commits, and the loop continues with the next message. |
| `/health` | `worker_instance` is None: 503. It is set and has a consumer: 200 `{"status": "healthy", "worker": "active"}`. `consumer` is None: 503. |
| `main()` config | With no env set, the worker gets `kafka:9092`, `mailpit`, `1025` and `noreply@image-platform.local`. With env set, the values come from `KAFKA_BOOTSTRAP_SERVERS`, `SMTP_HOST`, `SMTP_PORT` (cast to int) and `FROM_EMAIL`. |

## Behaviour to pin: cleanup-buckets
| Area | Behaviour |
|---|---|
| Kafka config | The consumer subscribes to `image.all.deleted`, group `image-cleanup-group`, with `enable_auto_commit=False`. The producer's serializer turns a dict into JSON bytes. |
| Deletes | `raw_s3_path` is deleted from the raw bucket. `processed_s3_path` and `preview_s3_path` are deleted from the processed bucket. A path that is `None` or empty is skipped. With only a raw path there is exactly one delete. The S3 client is created with the given `s3_config` kwargs. |
| Run loop | `start` comes first for both consumer and producer. A valid event is handled, then committed. Both are stopped when the iterator ends. |
| Invalid payload | A dict that doesn't validate goes to the DLQ: `send_and_wait("image.cleanup.failed", {...})` with `original_event` = the raw payload, `error` = `str(exc)`, `processor_version` = `1.0.0-py3.14.2-cleanup` and a `failed_at` timestamp. Then it is committed and the loop continues. |
| DLQ failure | If `send_and_wait` raises, it is logged at CRITICAL and not re-raised. The message is still committed. |
| `/health` | 503 when the worker is None, or when its consumer or producer is None. Otherwise 200 healthy. |

## Known bugs pinned
Each test gets `@pytest.mark.known_bug` and a `# CHARACTERIZATION: changes in <ID>` comment.

| Behaviour | Fixed by |
|---|---|
| Email goes to the hardcoded `developer@example.local`, not the image owner | N4 |
| A tombstone (`value=None`) or a non-dict JSON value (for example a list) raises inside the `except` handler (`msg.value.get`). The exception escapes `run()`, which stops the consumer and kills the worker. This is true for both workers. | R14 |
| The `value_deserializer` raises on `None` (tombstone) and on invalid JSON bytes, which would raise inside aiokafka's iterator | R14 |
| SMTP failure: logged, then committed. The message is lost, with no retry or DLQ. | R19 |
| S3 `delete_object` failure: `gather(return_exceptions=True)` swallows it and only logs. No DLQ, the message is committed, and "Purged S3 assets" is still logged. | R19 |
| A failed DLQ send still commits, so the event is lost | R19 |
| `/health` reports healthy based only on `consumer is not None`, even before `start()` or after `stop()` | R19 |
| A redelivered `image.avif.ready` sends a second email (no idempotency) | R15 |
| Cleanup `main()` hardcodes `kafka:9092`, the RustFS endpoint, the S3 access/secret keys and the bucket names. Env vars are ignored. | R2 / R11 |
| The cleanup S3 client is created once per event, not shared | R11 (note only, pinned through the `client()` call count) |
| `OUTPUT_TOPIC = "image.bucket.deleted"` is defined but never produced | R12 |
| `[project.scripts]` points to a hello-world `<pkg>.main()` stub. The Dockerfiles run `python -m <pkg>.main`. | R12 |

## Roadmap updates (done in this item)
- Add **R19 [S]**: "Workers stop losing failures: S3/SMTP errors and failed DLQ sends go to a DLQ or retry instead of being committed, and `/health` reflects the real consumer state".
- Tick F4 when done.
- `tech-stack.md`: remove "No tests for cleanup-buckets or email-notification".

## Acceptance criteria
1. `cd services/email-notification && uv run --extra dev pytest` and the same in `services/cleanup-buckets` both pass with no Docker stack and no network access.
2. Every row in both "Behaviour to pin" tables and in "Known bugs pinned" has at least one matching test. Each known-bug test has the `known_bug` marker and names its roadmap ID in a comment.
3. In each service, `pytest -m known_bug` selects only the known-bug tests, and no unknown-marker warning appears.
4. Each test file passes on its own and in any order.
5. `git diff --stat` shows changes only under `services/email-notification/tests/`, `services/cleanup-buckets/tests/`, this spec folder, `docs/product/roadmap.md` and `docs/product/tech-stack.md`. `uv.lock` is unchanged.
