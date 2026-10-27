# F3: Characterization tests for `rs_dpop`

## Goal
Pin what `shared_core.utils.endpoint.rs_dpop.validate_dpop` and `get_jkt` do today, with tests that need no running stack, so that R1, R3, R5, R7 and R12 can be checked against them. Tests describe what the code **does**, not what it should do.

## Scope
- `get_jkt(jwk)`: the RFC 7638 thumbprint for EC keys.
- `validate_dpop(request)`, mounted as a dependency on a test-only FastAPI app (`GET|POST /echo`, `GET /items/{id}`) that returns the claims it receives. Requests go through `httpx.AsyncClient(transport=ASGITransport(app), base_url="http://asset-service:8000")`, so `request.url` looks the way it does behind the BFF.
- Log output that leaks credentials (via `caplog`), as R3 baselines.

Code under test: `services/shared-core/src/shared_core/utils/endpoint/rs_dpop.py`. python-keycloak 7.1.1 `decode_token` fetches the JWKS through `certs()` and validates with jwcrypto: signature plus `exp`/`nbf` with a 60 s leeway, and no `iss`/`aud` check. Callers (`asset_service/api/projects.py`, `images.py`) use `dependencies=[Depends(validate_dpop)]` and discard the return value.

Test harness (`services/shared-core/tests/endpoint/`):
- `conftest.py`:
  - a session-scoped RS256 "realm" key.
  - a `keycloak` fixture that patches `rs_dpop.keycloak_openid.certs` to return its JWKS and `public_key` to return its base64 DER (the real Keycloak format). It counts calls and has a `raise_on` switch.
  - a guard that fails the test on any real call through `keycloak_openid.connection`.
  - the test-only `app` and the async `client`.
- `tests/conftest.py` registers the `known_bug` marker through `pytest_configure`, with the same wording as asset-service.
- `helpers.py`:
  - `make_access_token(claims, key=realm, cnf_key=...)` signs RS256 with PyJWT. Its defaults are `sub`, `iss`, `aud`, `exp` (+5 min) and `cnf.jkt` = the thumbprint of the DPoP key.
  - `make_proof(key, htm, htu, ath=..., **overrides)` signs ES256 with a `jwk` header. Its defaults are `typ: dpop+jwt`, `jti` and `iat`.
  - `ath(token)` returns the base64url SHA-256 of the token.
  - an independent RFC 7638 thumbprint, plus key generators (an RS256 realm key and a P-256 DPoP key).
- Proofs are built with PyJWT directly, because shared-core must not import bff-token-handler.

## Non-goals
- No changes under `src/`. Bugs are pinned, not fixed.
- No changes to asset-service or BFF tests. The end-to-end impersonation test belongs to R1/N2.
- No real Keycloak or network access, and no new dependencies. pyjwt, cryptography, httpx and pytest-asyncio are already in the environment. If httpx is only transitive, use it as-is and don't add it.
- No pytest `ini_options`, coverage or CI (F7, F8).
- The existing `tests/test_models.py` and `test_events.py` stay unchanged.

## Behaviour to pin
| Area | Behaviour |
|---|---|
| `get_jkt` | Matches an independently computed RFC 7638 thumbprint for a P-256 key. Extra members (`alg`, `use`, `kid`, `d`) don't change it. A missing `x` or `y` raises `KeyError`. |
| Header checks | A missing `Authorization` or `DPoP` header gives 401 `{"detail": "Missing Security Headers"}`. A scheme other than `DPoP ` (for example `Bearer`) gives 401 `"Expected DPoP Authorization"`. The scheme check is case-sensitive (`dpop x` gives 401). These details are **not** wrapped. |
| Happy path | A valid token and proof give 200, and the dependency returns the decoded access-token claims (including `sub` and `cnf`). This holds for GET and POST. The request's query string is ignored when the proof's `htu` has no query. |
| Access token | Each of these gives 401: a bad signature, the wrong realm key, a malformed token, `DPoP ` followed by an empty token, or an `exp` more than 60 s in the past. An `exp` 30 s in the past is accepted (jwcrypto's 60 s leeway). |
| Binding | A missing `cnf`, or a `cnf.jkt` for a different key, gives 401. |
| Proof | Each of these gives 401: a proof signed by a key other than the one in its `jwk` header, a non-ES256 proof (for example RS256 or HS256), a malformed proof, a proof whose `exp` claim is in the past, or a proof whose `iat` is in the future (PyJWT, no leeway). |
| `ath` / `htm` / `htu` | Each of these gives 401: a wrong or missing `ath`, a wrong `htm` (including lowercase `get`), or an `htu` with a different path, host or scheme. |
| Keycloak | Each request calls `public_key()` once and `certs()` once, with no cache. If either call raises (Keycloak down), the result is 401, not 5xx. The `public_key()` result is otherwise unused. |
| Error shape | Every failure inside the `try` gives 401 with the detail `"DPoP Validation Failed: <str(e)>"`. |

## Known bugs pinned
Each of these tests gets `@pytest.mark.known_bug` and a `# CHARACTERIZATION: changes in <ID>` comment. The refactor that fixes a bug flips its assertion on purpose.

| Behaviour | Fixed by |
|---|---|
| A `cnf`, `ath`, `htu` or `htm` mismatch raises `HTTPException` inside the `try`, so it gets re-wrapped and the detail becomes `"DPoP Validation Failed: 401: Token is not bound to this DPoP key"` (and similarly for the others) | R5 (widened) |
| Library error text reaches the client in `detail` (for example jwcrypto's signature and expiry messages, or `KeyError: 'jwk'`) | R5 (widened) |
| A wrong `iss`, and a wrong or missing `aud`, are accepted | R5 |
| A proof is accepted without `iat`, with an `iat` an hour old, or without `jti`. (An `iat` in the future is already rejected by PyJWT; *corrected during the build*) | R5 |
| The same proof is accepted twice (no `jti` replay cache) | R5 |
| A proof whose `htu` includes the query string (which is what the BFF sends) is rejected for a request that has a query string | R5 |
| The proof's `typ` is not checked (`typ: JWT`, or no `typ` at all, is accepted) | R5 (widened) |
| Two blocking Keycloak HTTP calls per request (`public_key()` and `certs()`), with no JWKS cache | R7 |
| When a header is missing or has the wrong scheme, the full `Authorization` value (the access token) is logged at WARNING. Successful requests log the realm public key, the ephemeral JWK and the full proof payload at INFO | R3 |
| The unreachable `if not dpop_jwt` branch, and the unused `key_obj` / `public_key()` lookup | R12 / R7 |
| The token's `sub` is returned, but callers discard it (`dependencies=[...]`) and take identity from `X-User-Sub` instead. Pinned only as "the return value contains `sub`", plus a comment | R1 |

## Roadmap updates (done in this item)
- R5 becomes: "Harden `rs_dpop`: check `iss`/`aud`, enforce an `iat` window, add a `jti` replay cache, check `typ`, fix the `htu` query-string mismatch, and return generic 401 details without re-wrapping".
- Tick F3 when done.

## Acceptance criteria
1. `cd services/shared-core && uv run --extra dev pytest` passes with no Docker stack and no network access. A guard fixture makes any real `keycloak_openid.connection` call fail the test.
2. Every row in "Behaviour to pin" and "Known bugs pinned" has at least one matching test. Each known-bug test has the `known_bug` marker and names its roadmap ID in a comment.
3. `pytest -m known_bug` selects only the known-bug tests, and no unknown-marker warning appears.
4. Each new test file passes on its own and in any order.
5. `git diff --stat` shows changes only under `services/shared-core/tests/`, this spec folder and `docs/product/roadmap.md`.
6. The existing shared-core tests still pass unchanged.
