"""
Single shared OAuth entry point for Gmail + Sheets — one consent grant
covers both (per project decision: reuse Gmail OAuth, no service account).

One-time interactive setup (run locally, needs a browser):
    python -m integrations.google_auth

That mints data/google_token.json. After that, ingest/gmail_client.py and
agent/tools/sheets.py only ever call get_credentials() — never trigger the
interactive flow themselves (that would hang a live server request).
"""
from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# gmail.modify alone covers read + label changes + send — no separate
# gmail.send scope needed, keeping the consent screen to two scopes total.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]

TOKEN_PATH = Path(__file__).resolve().parent.parent / "data" / "google_token.json"


class GoogleAuthNotConfigured(RuntimeError):
    pass


def _client_config() -> dict:
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise GoogleAuthNotConfigured(
            "GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET not set — see .env.example."
        )
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def is_configured() -> bool:
    """Cheap, no-network check: is there a cached token to load?"""
    return TOKEN_PATH.exists() and bool(os.environ.get("GMAIL_CLIENT_ID"))


def get_credentials() -> Credentials:
    """
    Load the cached token, refreshing it if expired. Never triggers the
    interactive consent flow — run `python -m integrations.google_auth`
    once from a terminal to create the token file first.
    """
    if not TOKEN_PATH.exists():
        raise GoogleAuthNotConfigured(
            f"No token at {TOKEN_PATH}. Run `python -m integrations.google_auth` "
            "once from a terminal to authorize Gmail + Sheets access."
        )

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except (ValueError, KeyError) as e:
        raise GoogleAuthNotConfigured(
            f"Token at {TOKEN_PATH} is malformed ({e}). "
            "Delete it and re-run `python -m integrations.google_auth`."
        ) from e
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds
    raise GoogleAuthNotConfigured(
        f"Token at {TOKEN_PATH} is invalid and can't be refreshed. "
        "Delete it and re-run `python -m integrations.google_auth`."
    )


def run_bootstrap_flow() -> Credentials:
    """
    One-time interactive setup: opens a browser for the user to grant
    Gmail + Sheets access, then caches the resulting token to TOKEN_PATH.
    CLI-only — never call this from a running server process.
    """
    flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    return creds


if __name__ == "__main__":
    run_bootstrap_flow()
    print(f"Authorized. Token saved to {TOKEN_PATH}")
