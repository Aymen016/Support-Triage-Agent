import sys
from pathlib import Path

import pytest

# so `agent.*` / `ingest.*` imports resolve when running `pytest` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.llm_client import FakeLLMClient


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture(autouse=True)
def _isolate_google_auth(tmp_path, monkeypatch):
    """
    Isolates every test from a developer's real .env/cached Google token —
    same rationale as tests/test_api.py's client fixture already isolating
    ANTHROPIC_API_KEY. Without this, a developer's real .env could silently
    flip existing tests onto the Gmail/Sheets code path.
    """
    from integrations import google_auth
    monkeypatch.setattr(google_auth, "TOKEN_PATH", tmp_path / "google_token.json")
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)
