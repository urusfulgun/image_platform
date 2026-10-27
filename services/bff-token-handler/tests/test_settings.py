"""BffSettings reads the client secret from env or a Docker secrets file."""

import pytest
from pydantic import ValidationError

from bff_token_handler.settings import BffSettings


def test_client_secret_is_required(monkeypatch):
    monkeypatch.delenv("CLIENT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="client_secret"):
        BffSettings(_secrets_dir=None)


def test_client_secret_from_env(monkeypatch):
    monkeypatch.setenv("CLIENT_SECRET", "from-env")

    assert BffSettings(_secrets_dir=None).client_secret == "from-env"


def test_client_secret_from_secrets_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
    (tmp_path / "client_secret").write_text("from-file")

    assert BffSettings(_secrets_dir=tmp_path).client_secret == "from-file"
