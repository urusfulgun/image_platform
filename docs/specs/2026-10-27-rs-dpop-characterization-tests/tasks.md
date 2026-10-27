# Tasks: F3 rs_dpop characterization tests

Spec: [spec.md](spec.md)

- [x] 1. In `services/shared-core/tests/conftest.py`, register the `known_bug` marker through `pytest_configure`, with the same wording as asset-service. Check that `pytest --markers` lists it and that the existing tests still pass.
- [x] 2. Add `tests/endpoint/helpers.py` with `ath()`, `make_access_token()`, `make_proof()`, an independent RFC 7638 thumbprint, and key generators (an RS256 realm key and a P-256 DPoP key).
- [x] 3. Add `tests/endpoint/conftest.py` with:
  - the session-scoped realm key
  - the `keycloak` patch fixture: `certs`/`public_key`, call counts and a `raise_on` switch
  - a no-network guard on `keycloak_openid.connection`
  - the test-only `app` with `/echo` and `/items/{id}`
  - the async `client` (`ASGITransport`, `base_url="http://asset-service:8000"`)

  Prove that the fixtures work with one happy-path test.
- [x] 4. `test_get_jkt.py`:
  - Matches RFC 7638.
  - Extra members are ignored.
  - A missing member raises `KeyError`.
- [x] 5. `test_headers.py`:
  - Missing `Authorization`, missing `DPoP`, the `Bearer` scheme and a lowercase scheme, each with its exact unwrapped detail.
  - `known_bug` R3: the access token appears in the WARNING log.
- [x] 6. `test_access_token.py`:
  - The happy path returns the claims, including `sub` (GET, POST, and with the query ignored). Add the R1 comment that callers discard them.
  - Bad signature, wrong realm key, malformed token and empty token.
  - Expired beyond the leeway, and expired within it.
  - A missing `cnf` and a foreign `cnf`.
  - `known_bug` R5: a wrong `iss` or `aud` is accepted, the detail is re-wrapped, and library text leaks into it.
- [x] 7. `test_proof.py`:
  - Wrong signer, non-ES256 algorithm, malformed proof and past `exp`.
  - `ath`, `htm` and `htu` mismatches.
  - `known_bug` R5: a missing, old or future `iat` is accepted, a missing `jti` is accepted, a replayed proof is accepted, `typ` is unchecked, and an `htu` with a query is rejected.
- [x] 8. `test_keycloak_calls.py`:
  - `known_bug` R7: one `public_key()` and one `certs()` call per request, checked across two requests.
  - Either call raising gives 401.
  - `known_bug` R3: the realm key, the JWK and the proof payload are logged at INFO.
- [x] 9. Run each new file on its own, then the full suite, then `pytest -m known_bug`. Check that every row in "Known bugs pinned" has a test.
- [x] 10. Update `docs/product/roadmap.md`: widen R5's text and tick F3. Check the acceptance criteria (no `src/` diff).
