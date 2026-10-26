# F2: Characterization tests for the BFF

## Goal
Pin the current HTTP behaviour of bff-token-handler's login, callback, `/me` and proxy routes, including exactly which headers the proxy forwards to AssetService, with tests that need no running stack. Later refactors (R1, R3, R6, R7, R8, R17, R18) can be checked against them. Tests describe what the code **does**, not what it should do.

## Scope
Routes, exercised through the real FastAPI `app` (`bff_token_handler.main`) with `fastapi.testclient.TestClient(app, raise_server_exceptions=False)`, `follow_redirects=False`, not used as a context manager, so the lifespan does not run.
- `GET /health`
- `GET /login`
- `GET /authorization-code/callback`
- `GET /me`
- `GET|POST|PUT|PATCH|DELETE /proxy/{path}`
- Log output that leaks credentials (via `caplog`), as R3 baselines

`/logout` is already covered by `tests/test_logout.py`, which stays unchanged.

Test harness (`tests/api/conftest.py` + `tests/api/helpers.py`):
- `FakeRedis`: an async `get`/`setex`/`delete` over a dict that also records TTLs and stores `str` values (the real client uses `decode_responses=True`).
- `app.state.session_store = SessionStore(fake)` and `app.state.verifier_store = CodeVerifierStore(fake)`, so sessions go through the real `SessionData` and key-pair marshalling round trip.
- `app.state.ec_key_pair = generate_ec_key_pair()`.
- `app.state.keycloak_openid`: a real `KeycloakOpenID` built from `settings`, with `well_known` stubbed (as in `tests/test_oauth.py`).
- Each fixture restores `app.state` on teardown. `test_logout.py` overwrites `session_store` without restoring it, so order independence matters.
- Keycloak calls are patched where `main` uses them: `main.exchange_code` and `main.introspect_token`.
- Upstream: capture the real `httpx.AsyncClient` first, then patch `bff_token_handler.proxy.reverse_proxy.httpx.AsyncClient` with a factory that returns `real(transport=httpx.MockTransport(handler), **kw)`. The handler records every outgoing `httpx.Request` and returns a configurable response.
- Helpers:
  - `make_id_token(claims)` builds an unsigned compact JWS-shaped string. The BFF decodes it without verifying it.
  - `seed_session(...)` calls `SessionStore.create` and returns `(sid, token_set, key_pair)`.
  - `decode_proof(...)` returns the header and payload of a DPoP proof.
- The `known_bug` marker is registered in `tests/conftest.py` through `pytest_configure`, with the same text as asset-service.

## Non-goals
- No changes under `src/`. Bugs are pinned, not fixed.
- No tests of `rs_dpop` (F3), `auth/oauth.py` internals beyond what the routes show, the lifespan, or CORS.
- No real Redis, Keycloak or network access, and no new dependencies.
- No pytest `ini_options`, coverage or CI (F7, F8).
- `tests/test_logout.py`, `test_dpop.py` and `test_oauth.py` stay unchanged.

## Behaviour to pin
| Area | Behaviour |
|---|---|
| Health | `GET /health` → 200 `{"status": "ok"}`. |
| Login | Returns 307 to Keycloak's `authorization_endpoint` with `response_type=code`, `client_id=bff-client`, `redirect_uri=settings.redirect_uri`, `scope=openid`, a fresh `state`, `code_challenge_method=S256` and `code_challenge`. It stores `pkce:{state}` with TTL 300, and `code_challenge` = S256(stored verifier). Two logins give different `state` values. No cookie is set. |
| Callback: errors | An unknown `state` gives 400 `{"detail": "Invalid or expired state"}`, and `exchange_code` is not called. A missing `code` or `state` gives 422. An `exchange_code` that raises `KeycloakPostError` gives 500, and no session or cookie is created. |
| Callback: success | `exchange_code` is awaited with `(code, stored verifier, app.state.ec_key_pair)`. A `session:{sid}` entry is written with TTL `session_ttl_seconds`, and it round-trips to the same `TokenSet` and key. The response is 307 `Location: /` with `Set-Cookie: sid=<sid>; HttpOnly; Max-Age=3600; Path=/; SameSite=strict` and no `Secure`. |
| `/me` | No cookie gives 401 `{"detail": "Not authenticated"}`. `introspect_token` is awaited with `(session key_pair, access_token)`. A dict result gives 200 `{"id_token": <UserProfileResponse fields>}` with extra claims (`sub`, `iss`) dropped. A JWS string result is decoded **without verification** and gives the same shape. `KeycloakAuthenticationError(response_code=401)` gives 401 `{"detail": "Not authenticated extra: <msg>"}`. Claims missing a required profile field give 500. |
| Proxy: routing | No cookie gives 401 `{"detail": "Not authenticated"}`, and no upstream call is made. The upstream URL is `asset_service_url + "/" + path`, keeping the query string. The method and raw body are forwarded unchanged for GET/POST/PUT/PATCH/DELETE, and `HEAD` gives 405. The upstream status, body and `content-type` are mirrored, and a 404 from upstream passes through as 404. A session with `id_token=None` gives 500. An upstream `httpx.ConnectError` gives 500. |
| Proxy: auth headers | `Authorization: DPoP <access_token>`, and a client `Authorization` header is dropped. The `DPoP` proof has `htm` = the method, `htu` = the full upstream URL **including the query**, `ath` = `generate_dpop_ath(access_token)`, a `jwk` thumbprint equal to the session key, and a signature that verifies against that key. `X-User-Sub` is the `sub` of the session's (unverified) id_token. `host`, `connection` and `transfer-encoding` are dropped. Other client headers (e.g. `x-custom`, `content-type`) are forwarded. |

## Known bugs pinned
Each of these tests gets `@pytest.mark.known_bug` and a `# CHARACTERIZATION: changes in <ID>` comment. The refactor that fixes a bug flips its assertion on purpose.

| Behaviour | Fixed by |
|---|---|
| A client-supplied `X-User-Sub` is forwarded **next to** the BFF's own, so upstream gets two values and the client's comes first | R1 |
| A client-supplied `DPoP` header is forwarded next to the BFF's proof | R1 |
| The browser `Cookie` header (including `sid`) is forwarded to AssetService | R1 (widened) |
| Upstream response headers are copied verbatim (`content-encoding`, `content-length`, …), so a gzipped upstream reply arrives with `content-encoding: gzip` over an already-decoded body | R17 (new) |
| Every session stores the **same** process-wide `app.state.ec_key_pair`, so one leaked private key unbinds every user's DPoP tokens. *Reclassified after the build.* | R18 (new) |
| `/me` with a cookie whose session is gone gives 500, not 401 | R8 |
| `/proxy` with a cookie whose session is gone gives 500, not 401 | R8 |
| The PKCE state is not deleted after use, so a second callback with the same `state` creates a second session | R8 |
| The callback logs the authorization `code` and PKCE verifier, before the state check | R3 |
| The proxy logs the `sid` and the full forward headers, including the access token | R3 |
| `introspect_token` logs the full DPoP proof | R3 |

## Roadmap updates (done in this item)
- R1 becomes: "…and the proxy strips client identity, DPoP and `Cookie` headers".
- Add after R16: `- [ ] R17 [S] BFF proxy filters upstream response headers (hop-by-hop, content-encoding/content-length) instead of copying them verbatim`.
- Add after R17: `- [ ] R18 [S] BFF generates a fresh DPoP key pair per session at callback instead of sharing one process-wide key`.
- Tick F2 when done.

## Acceptance criteria
1. `cd services/bff-token-handler && uv run --extra dev pytest` passes with no Docker stack and no network access.
2. Every route in Scope has at least one success test and one failure test.
3. Every row in "Behaviour to pin" and "Known bugs pinned" has at least one matching test. Each known-bug test has the `known_bug` marker and names its roadmap ID in a comment.
4. `pytest -m known_bug` selects only the known-bug tests, and no unknown-marker warning appears.
5. Each new test file passes on its own, and `tests/api` passes together with `test_logout.py` when the two are run explicitly in either order.
6. `git diff --stat` shows changes only under `services/bff-token-handler/tests/`, this spec folder and `docs/product/roadmap.md`.
7. The existing 25 tests still pass unchanged.
