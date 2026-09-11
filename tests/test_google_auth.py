import datetime
import json

import pytest
from google.oauth2.credentials import Credentials

from integrations import google_auth
from integrations.google_auth import GoogleAuthNotConfigured, get_credentials, is_configured


def _write_token(tmp_path, monkeypatch, *, expiry=None, refresh_token="refresh-tok"):
    token_path = tmp_path / "google_token.json"
    monkeypatch.setattr(google_auth, "TOKEN_PATH", token_path)
    creds = Credentials(
        token="access-tok",
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret="client-secret",
        scopes=google_auth.SCOPES,
        expiry=expiry,
    )
    token_path.write_text(creds.to_json())
    return token_path


def test_is_configured_false_when_no_token(tmp_path, monkeypatch):
    monkeypatch.setattr(google_auth, "TOKEN_PATH", tmp_path / "google_token.json")
    monkeypatch.setenv("GMAIL_CLIENT_ID", "x")
    assert is_configured() is False


def test_is_configured_false_when_no_client_id(tmp_path, monkeypatch):
    _write_token(tmp_path, monkeypatch)
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    assert is_configured() is False


def test_is_configured_true_when_token_and_client_id_present(tmp_path, monkeypatch):
    _write_token(tmp_path, monkeypatch)
    monkeypatch.setenv("GMAIL_CLIENT_ID", "x")
    assert is_configured() is True


def test_get_credentials_raises_when_no_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(google_auth, "TOKEN_PATH", tmp_path / "google_token.json")
    with pytest.raises(GoogleAuthNotConfigured):
        get_credentials()


def test_get_credentials_returns_valid_token_without_refresh(tmp_path, monkeypatch):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    _write_token(tmp_path, monkeypatch, expiry=future)
    creds = get_credentials()
    assert creds.token == "access-tok"


def test_get_credentials_refreshes_expired_token_and_persists_it(tmp_path, monkeypatch):
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    token_path = _write_token(tmp_path, monkeypatch, expiry=past)

    def fake_refresh(self, request):
        self.token = "refreshed-tok"
        self.expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)

    creds = get_credentials()

    assert creds.token == "refreshed-tok"
    saved = json.loads(token_path.read_text())
    assert saved["token"] == "refreshed-tok"


def test_get_credentials_raises_when_malformed_token_missing_refresh_token(tmp_path, monkeypatch):
    """from_authorized_user_file requires refresh_token in the file's JSON —
    a token with none (e.g. hand-edited/corrupted) must surface as our own
    clear error, not a raw ValueError from the google-auth library."""
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    _write_token(tmp_path, monkeypatch, expiry=past, refresh_token=None)
    with pytest.raises(GoogleAuthNotConfigured):
        get_credentials()


def test_client_config_raises_when_client_id_missing(monkeypatch):
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    with pytest.raises(GoogleAuthNotConfigured):
        google_auth._client_config()
