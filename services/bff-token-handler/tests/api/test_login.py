"""Characterization: GET /login starts Auth Code + PKCE."""

import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

from helpers import AUTH_ENDPOINT

from bff_token_handler.settings import settings


def _redirect_params(resp) -> tuple[str, dict[str, str]]:
    url = urlsplit(resp.headers["location"])
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    return f"{url.scheme}://{url.netloc}{url.path}", params


def test_login_redirects_to_keycloak_with_pkce(client):
    resp = client.get("/login")

    assert resp.status_code == 307
    target, params = _redirect_params(resp)
    assert target == AUTH_ENDPOINT
    assert params["response_type"] == "code"
    assert params["client_id"] == settings.client_id == "bff-client"
    assert params["redirect_uri"] == settings.redirect_uri
    assert params["scope"] == "openid"
    assert params["code_challenge_method"] == "S256"
    assert params["state"]
    assert params["code_challenge"]


def test_login_stores_verifier_under_state(client, fake_redis):
    resp = client.get("/login")

    _, params = _redirect_params(resp)
    key = f"pkce:{params['state']}"
    assert fake_redis.keys("pkce:") == [key]
    assert fake_redis.ttls[key] == 300

    verifier = fake_redis.data[key]
    digest = hashlib.sha256(verifier.encode()).digest()
    assert (
        params["code_challenge"]
        == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    )


def test_login_uses_fresh_state_each_time(client, fake_redis):
    _, first = _redirect_params(client.get("/login"))
    _, second = _redirect_params(client.get("/login"))

    assert first["state"] != second["state"]
    assert first["code_challenge"] != second["code_challenge"]
    assert len(fake_redis.keys("pkce:")) == 2


def test_login_sets_no_cookie(client):
    resp = client.get("/login")

    assert "set-cookie" not in resp.headers
