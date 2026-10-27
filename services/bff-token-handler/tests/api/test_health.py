"""Characterization: GET /health, and a check that the fixtures wire up."""

from bff_token_handler import main


def test_health(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_app_state_uses_fakes(app_state, fake_redis):
    assert main.app.state.session_store is app_state.session_store
    assert main.app.state.session_store._redis is fake_redis
