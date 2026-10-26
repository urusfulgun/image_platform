# Tasks: F2 BFF characterization tests

Spec: [spec.md](spec.md)

- [ ] 1. In `tests/conftest.py`, register the `known_bug` marker through `pytest_configure`, with the same wording as asset-service. Check that `pytest --markers` lists it and the existing 25 tests still pass.
- [ ] 2. Add `tests/api/helpers.py` with `FakeRedis` (get/setex/delete, recording TTLs), `make_id_token(claims)`, `decode_proof(proof)` and the profile-claims constants.
- [ ] 3. Add `tests/api/conftest.py` with fixtures for:
  - `fake_redis`
  - `app_state`: the real stores, `ec_key_pair` and a `keycloak_openid` with `well_known` stubbed, all restored on teardown
  - `client`: `TestClient` with `raise_server_exceptions=False` and `follow_redirects=False`
  - `seed_session`
  - `upstream`: the MockTransport patch, with recorded requests and a settable response
  - `exchange_code`/`introspect_token` patches on `main`

  Prove the fixtures work with `tests/api/test_health.py`.
- [ ] 4. `tests/api/test_login.py`:
  - The 307 target and every query param.
  - The stored `pkce:{state}` with TTL 300, and S256(verifier) == challenge.
  - Unique state per call, and no cookie.
- [ ] 5. `tests/api/test_callback.py`:
  - Unknown state → 400, with no exchange.
  - Missing params → 422.
  - Success: the `exchange_code` args, the session written with its TTL and round-trip, the 307 to `/`, and the exact cookie attributes.
  - Every session reuses `app.state.ec_key_pair`.
  - `KeycloakPostError` → 500, with no session.
  - `known_bug` R8: PKCE reuse.
  - `known_bug` R3: code and verifier logged.
- [ ] 6. `tests/api/test_me.py`:
  - No cookie → 401.
  - Dict claims → 200 with the `id_token` shape and internal claims dropped.
  - JWS string claims → the same shape.
  - `KeycloakAuthenticationError` → status passthrough with the "Not authenticated extra" detail.
  - Missing profile field → 500.
  - `known_bug` R8: gone session → 500.
- [ ] 7. `tests/api/test_proxy.py`:
  - No cookie → 401 with no upstream call.
  - URL building with path and query.
  - The method and body for each of GET/POST/PUT/PATCH/DELETE, and `HEAD` → 405.
  - Status, body and content-type mirrored, including an upstream 404.
  - `id_token=None` → 500, and `ConnectError` → 500.
  - `known_bug` R8: gone session → 500.
  - `known_bug` R3: sid and access token in the logs, and the DPoP proof logged by `introspect_token`. Put the last one here or in `test_me.py`, using the real `introspect_token` with `dpop_user_info` patched.
- [ ] 8. `tests/api/test_proxy_headers.py`:
  - `Authorization: DPoP <at>` replaces the client's.
  - DPoP proof claims (`htm`, `htu` with the query, `ath`, jwk = the session key, a verifying signature).
  - `X-User-Sub` = the id_token `sub`.
  - Hop-by-hop headers dropped and custom headers forwarded.
  - `known_bug` R1: duplicated `x-user-sub` (client value first), duplicated `dpop`, `cookie` with the `sid` forwarded.
  - `known_bug` R17: upstream response headers copied verbatim (gzip `content-encoding` over a decoded body).
- [ ] 9. Run each new file on its own, then `tests/api` + `test_logout.py` in both orders, then the full suite. Run `pytest -m known_bug` and check that every known-bugs row has a test.
- [ ] 10. Update `docs/product/roadmap.md`: widen R1's text to include `Cookie`, add R17, and tick F2. Check the acceptance criteria (no `src/` diff).
