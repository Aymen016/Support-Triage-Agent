import pytest

from api.db import (
    GateError, SendError, approve_email, escalate_email_manually, get_email, init_db,
    list_emails, make_session_factory, reject_email, save_loop_result, session_scope,
)
from agent.llm_client import FakeLLMClient
from agent.orchestrator import ScriptedOrchestrator
from agent.loop import run_agent_loop
from agent.schemas import IncomingEmail
from ingest.fixture_loader import load_fixtures


def _gmail_email(id="gm_1", thread_id="thread_1"):
    """A Gmail-sourced email — distinct from fixtures, which always default
    to source='fixture' and must never trigger a real send attempt."""
    return IncomingEmail(
        id=id, from_address="customer@example.com", subject="Help resetting my password",
        body="I can't log in, please help", thread_id=thread_id, source="gmail",
    )


@pytest.fixture
def db_session_factory(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    init_db(engine)
    # log_to_sheet writes to a local CSV by default — redirect it into tmp_path
    # so these tests don't pollute the real repo's data/ directory.
    monkeypatch.setattr("agent.tools.sheets.LOCAL_LOG_PATH", tmp_path / "sheet_log.csv")
    return make_session_factory(engine)


def _run_and_save(session_factory, email, llm):
    result = run_agent_loop(email, orchestrator=ScriptedOrchestrator(), llm=llm)
    with session_scope(session_factory) as session:
        save_loop_result(session, email, result)
    return result


def test_save_loop_result_persists_email_classification_and_steps(db_session_factory):
    llm = FakeLLMClient()
    email = load_fixtures()[15]  # routine password reset -> should draft
    result = _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        row = get_email(session, email.id)
        assert row is not None
        assert row.status == "pending"  # drafted, awaiting human review — NOT sent
        assert row.classification is not None
        assert row.draft is not None
        assert row.draft.status == "pending"
        assert len(row.steps) == len(result.steps)


def test_approve_email_marks_sent_and_only_approve_does(db_session_factory):
    llm = FakeLLMClient()
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        row = approve_email(session, email.id, approver="jane@smallbiz.com")
        assert row.status == "approved"
        assert row.draft.status == "approved"
        assert row.draft.approver == "jane@smallbiz.com"


def test_cannot_approve_an_already_decided_draft(db_session_factory):
    llm = FakeLLMClient()
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        approve_email(session, email.id, approver="jane@smallbiz.com")

    with session_scope(db_session_factory) as session:
        with pytest.raises(GateError):
            approve_email(session, email.id, approver="jane@smallbiz.com")


def test_approve_with_edit_stores_edited_text_not_original(db_session_factory):
    llm = FakeLLMClient()
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        row = approve_email(session, email.id, approver="jane@smallbiz.com", edited_text="A hand-edited reply.")
        assert row.draft.edited_text == "A hand-edited reply."
        assert row.draft.final_text == "A hand-edited reply."


def test_reject_email_stores_rejection_for_improvement_dataset(db_session_factory):
    llm = FakeLLMClient()
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        row = reject_email(session, email.id, approver="jane@smallbiz.com", reason="wrong tone")
        assert row.status == "rejected"
        assert row.draft.status == "rejected"


def test_escalated_email_has_no_draft_to_approve(db_session_factory):
    llm = FakeLLMClient()
    # em_036 is spam - the scripted orchestrator still runs classify->extract->search->draft,
    # so to get a real escalation deterministically we use a genuinely low-confidence one.
    # Simplest: manually escalate a drafted email instead, exercising that path.
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        row = escalate_email_manually(session, email.id, reason="human noticed this needs legal review")
        assert row.status == "escalated"
        assert row.escalation is not None
        assert row.draft.status == "rejected"  # superseded

    with session_scope(db_session_factory) as session:
        with pytest.raises(GateError):
            approve_email(session, email.id, approver="someone")


def test_approve_gmail_sourced_email_sends_real_reply(db_session_factory, monkeypatch):
    llm = FakeLLMClient()
    email = _gmail_email()
    _run_and_save(db_session_factory, email, llm)

    sent_calls = []
    monkeypatch.setattr("api.db.google_auth.is_configured", lambda: True)
    monkeypatch.setattr(
        "api.db.gmail_client.send_reply",
        lambda **kwargs: sent_calls.append(kwargs) or {"id": "sent-1"},
    )

    with session_scope(db_session_factory) as session:
        row = approve_email(session, email.id, approver="jane@smallbiz.com")
        assert row.status == "approved"

    assert len(sent_calls) == 1
    assert sent_calls[0]["original_message_id"] == email.id
    assert sent_calls[0]["thread_id"] == "thread_1"
    assert sent_calls[0]["to_address"] == "customer@example.com"


def test_approve_gmail_sourced_email_send_failure_blocks_approval(db_session_factory, monkeypatch):
    llm = FakeLLMClient()
    email = _gmail_email(id="gm_2")
    _run_and_save(db_session_factory, email, llm)

    monkeypatch.setattr("api.db.google_auth.is_configured", lambda: True)

    def _boom(**kwargs):
        raise RuntimeError("token expired")

    monkeypatch.setattr("api.db.gmail_client.send_reply", _boom)

    with session_scope(db_session_factory) as session:
        with pytest.raises(SendError):
            approve_email(session, email.id, approver="jane@smallbiz.com")

    with session_scope(db_session_factory) as session:
        row = get_email(session, email.id)
        assert row.status == "pending"  # not falsely marked approved
        assert row.draft.status == "pending"


def test_approve_fixture_sourced_email_never_attempts_real_send(db_session_factory, monkeypatch):
    llm = FakeLLMClient()
    email = load_fixtures()[15]
    _run_and_save(db_session_factory, email, llm)

    sent_calls = []
    monkeypatch.setattr("api.db.google_auth.is_configured", lambda: True)  # even if "configured"
    monkeypatch.setattr("api.db.gmail_client.send_reply", lambda **kwargs: sent_calls.append(kwargs))

    with session_scope(db_session_factory) as session:
        row = approve_email(session, email.id, approver="jane@smallbiz.com")
        assert row.status == "approved"

    assert sent_calls == []  # fixture-sourced — never a real send attempt


def test_list_emails_filters_by_status(db_session_factory):
    llm = FakeLLMClient()
    emails = load_fixtures()[:5]
    for email in emails:
        _run_and_save(db_session_factory, email, llm)

    with session_scope(db_session_factory) as session:
        pending = list_emails(session, status="pending")
        escalated = list_emails(session, status="escalated")
        all_rows = list_emails(session)
        assert len(pending) + len(escalated) == len(all_rows) == 5
