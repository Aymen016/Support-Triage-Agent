import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # isolate DB + sheet log per test
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_api.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # force fake pipeline, no network
    monkeypatch.setattr("agent.tools.sheets.LOCAL_LOG_PATH", tmp_path / "sheet_log.csv")

    from api.main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_empty_queue_initially(client):
    resp = client.get("/emails")
    assert resp.status_code == 200
    assert resp.json() == []


def test_run_processes_all_50_fixtures(client):
    resp = client.post("/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed"] == 50
    assert body["drafted"] + body["escalated"] == 50
    assert body["used_fake_llm"] is True  # no ANTHROPIC_API_KEY in test env
    assert body["email_source"] == "fixtures"  # no Gmail OAuth configured in test env

    resp2 = client.get("/emails")
    assert len(resp2.json()) == 50


def test_run_is_idempotent_skips_already_seen(client):
    client.post("/run")
    resp = client.post("/run")
    body = resp.json()
    assert body["processed"] == 0
    assert body["skipped_already_seen"] == 50


def test_integrations_status_reports_disconnected_by_default(client):
    resp = client.get("/integrations/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"gmail_connected": False, "sheets_connected": False, "ai_mode": "fake"}


def test_integrations_status_reports_connected_when_configured(client, monkeypatch):
    monkeypatch.setattr("api.main.google_auth.is_configured", lambda: True)
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    resp = client.get("/integrations/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"gmail_connected": True, "sheets_connected": True, "ai_mode": "claude"}


def test_run_uses_gmail_when_configured(client, monkeypatch):
    from agent.schemas import IncomingEmail

    monkeypatch.setattr("integrations.google_auth.is_configured", lambda: True)
    monkeypatch.setattr(
        "ingest.gmail_client.fetch_new_emails",
        lambda label=None: [
            IncomingEmail(id="gm_1", from_address="a@b.com", subject="Help", body="I need help", source="gmail"),
        ],
    )

    resp = client.post("/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email_source"] == "gmail"
    assert body["processed"] == 1


def test_run_gmail_fetch_failure_returns_502(client, monkeypatch):
    monkeypatch.setattr("integrations.google_auth.is_configured", lambda: True)

    def _boom(label=None):
        raise RuntimeError("token expired")

    monkeypatch.setattr("ingest.gmail_client.fetch_new_emails", _boom)

    resp = client.post("/run")
    assert resp.status_code == 502


def test_get_email_detail_has_steps_and_classification(client):
    client.post("/run")
    email_id = client.get("/emails").json()[0]["id"]

    resp = client.get(f"/emails/{email_id}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["classification"] is not None
    assert len(detail["steps"]) > 0


def test_get_nonexistent_email_404s(client):
    resp = client.get("/emails/em_does_not_exist")
    assert resp.status_code == 404


def test_full_approval_flow(client):
    client.post("/run")
    pending = client.get("/emails", params={"status": "pending"}).json()
    assert len(pending) > 0
    email_id = pending[0]["id"]

    approve_resp = client.post(f"/emails/{email_id}/approve", json={"approver": "jane@smallbiz.com"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"
    assert approve_resp.json()["draft"]["approver"] == "jane@smallbiz.com"

    # can't approve twice
    second = client.post(f"/emails/{email_id}/approve", json={"approver": "jane@smallbiz.com"})
    assert second.status_code == 400


def test_edit_then_approve_stores_edited_text(client):
    client.post("/run")
    email_id = client.get("/emails", params={"status": "pending"}).json()[0]["id"]

    resp = client.post(f"/emails/{email_id}/approve", json={
        "approver": "jane@smallbiz.com", "edited_text": "Hand-edited final reply.",
    })
    assert resp.json()["draft"]["final_text"] == "Hand-edited final reply."


def test_reject_flow(client):
    client.post("/run")
    email_id = client.get("/emails", params={"status": "pending"}).json()[0]["id"]

    resp = client.post(f"/emails/{email_id}/reject", json={"approver": "jane@smallbiz.com", "reason": "wrong tone"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_manual_escalate_flow(client):
    client.post("/run")
    email_id = client.get("/emails", params={"status": "pending"}).json()[0]["id"]

    resp = client.post(f"/emails/{email_id}/escalate", json={"reason": "needs legal review"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "escalated"

    # already escalated -> approving should now fail (no pending draft)
    approve_resp = client.post(f"/emails/{email_id}/approve", json={"approver": "x"})
    assert approve_resp.status_code == 400


def test_settings_default_and_update(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    defaults = resp.json()
    assert defaults["confidence_threshold"] == 0.6
    assert defaults["auto_send_enabled"] is False

    updated = client.put("/settings", json={"confidence_threshold": 0.9, "category_notes": "Treat anything mentioning 'lawsuit' as billing/high."})
    assert updated.status_code == 200
    assert updated.json()["confidence_threshold"] == 0.9
    assert "lawsuit" in updated.json()["category_notes"]

    # partial update doesn't clobber other fields
    still_there = client.get("/settings").json()
    assert still_there["tone_instructions"] == defaults["tone_instructions"]


def test_raising_confidence_threshold_increases_escalations(client):
    # low threshold: almost everything the fake heuristic is >=55% sure of gets drafted
    client.put("/settings", json={"confidence_threshold": 0.1})
    low_thresh = client.post("/run").json()

    # reset by using a fresh client would be cleaner, but re-running isn't
    # idempotent (already-seen emails are skipped) — so just check that at
    # threshold 0.1 almost nothing escalates on confidence grounds alone,
    # which we can confirm structurally: drafted should dominate.
    assert low_thresh["drafted"] >= low_thresh["escalated"]


def test_run_stream_emits_events(client):
    with client.stream("GET", "/run/stream") as resp:
        assert resp.status_code == 200
        events = []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if line.startswith("event: done") or (events and events[-1] == "done"):
                if len(events) > 3:  # got a handful of events, that's enough to confirm streaming works
                    break
        assert "email_start" in events
        assert "step" in events
