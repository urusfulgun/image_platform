"""Characterization: /proxy/{path} routing, body forwarding and response mirroring."""

import logging

import httpx
import pytest

from bff_token_handler.settings import settings
from tests.api.helpers import make_token_set

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def test_proxy_without_cookie_is_401(client, upstream):
    resp = client.get("/proxy/projects/")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}
    assert upstream.requests == []


def test_proxy_builds_upstream_url_with_query(client, seed_session, upstream):
    seed_session()

    client.get("/proxy/projects/abc/images/preview", params={"page": "2", "q": "a b"})

    assert settings.asset_service_url == "http://asset-service:8000"
    assert str(upstream.last.url) == (
        "http://asset-service:8000/projects/abc/images/preview?page=2&q=a+b"
    )


@pytest.mark.parametrize("method", METHODS)
def test_proxy_forwards_method_and_body(client, seed_session, upstream, method):
    seed_session()
    body = b'{"name": "holiday"}'

    resp = client.request(method, "/proxy/projects/", content=body)

    assert resp.status_code == 200
    assert upstream.last.method == method
    assert upstream.last.content == body


def test_proxy_rejects_head(client, seed_session, upstream):
    seed_session()

    resp = client.head("/proxy/projects/")

    assert resp.status_code == 405
    assert upstream.requests == []


def test_proxy_mirrors_upstream_response(client, seed_session, upstream):
    seed_session()
    upstream.reply = lambda request: httpx.Response(
        201, content=b'{"id": 1}', headers={"content-type": "application/vnd.test+json"}
    )

    resp = client.post("/proxy/projects/", json={"name": "x"})

    assert resp.status_code == 201
    assert resp.content == b'{"id": 1}'
    assert resp.headers["content-type"] == "application/vnd.test+json"


def test_proxy_passes_upstream_404_through(client, seed_session, upstream):
    seed_session()
    upstream.reply = lambda request: httpx.Response(
        404, json={"detail": "Project not found"}
    )

    resp = client.get("/proxy/projects/missing")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Project not found"}


def test_proxy_with_session_without_id_token_is_500(client, seed_session, upstream):
    seed_session(make_token_set(id_token=None))

    resp = client.get("/proxy/projects/")

    assert resp.status_code == 500
    assert upstream.requests == []


def test_proxy_upstream_connect_error_is_500(client, seed_session, upstream):
    seed_session()

    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    upstream.reply = refuse

    resp = client.get("/proxy/projects/")

    assert resp.status_code == 500


@pytest.mark.known_bug
def test_proxy_with_gone_session_is_500(client, upstream):
    # CHARACTERIZATION: changes in R8 (expired session returns 401)
    client.cookies.set(settings.session_cookie_name, "no-such-session")

    resp = client.get("/proxy/projects/")

    assert resp.status_code == 500
    assert upstream.requests == []


@pytest.mark.known_bug
def test_proxy_logs_sid_and_access_token(client, seed_session, upstream, caplog):
    # CHARACTERIZATION: changes in R3 (stop logging tokens, cookies and full headers)
    caplog.set_level(logging.INFO, logger="bff_token_handler.proxy.reverse_proxy")
    session = seed_session()

    client.get("/proxy/projects/")

    assert f"SID ---> {session.sid}" in caplog.text
    assert f"DPoP {session.token_set.access_token}" in caplog.text
