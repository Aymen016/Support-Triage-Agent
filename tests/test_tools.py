import csv

from agent.schemas import (
    ClassifyInput, ClassifyOutput,
    ExtractInput, ExtractOutput,
    DraftReplyInput, DraftReplyOutput,
    KBSearchInput, KBSearchOutput,
    LogToSheetInput, LogToSheetOutput,
    EscalateInput, EscalateOutput,
    ToolError,
)
from agent.tools.classify import classify_email
from agent.tools.extract import extract_customer_info
from agent.tools.draft import draft_reply
from agent.tools.knowledge_base import search_knowledge_base
from agent.tools.sheets import log_to_sheet, LOCAL_LOG_PATH
from agent.tools.escalate import escalate_to_human
from ingest.fixture_loader import load_fixtures, load_fixtures_with_labels


# ---------------------------------------------------------------------------
# classify_email
# ---------------------------------------------------------------------------

def test_classify_email_returns_valid_output(fake_llm):
    result = classify_email(
        ClassifyInput(subject="URGENT checkout down", body="site is down, losing sales"),
        llm=fake_llm,
    )
    assert isinstance(result, ClassifyOutput)
    assert result.urgency == "high"
    assert 0.0 <= result.confidence <= 1.0


def test_classify_email_on_all_fixtures_produces_valid_schema(fake_llm):
    # Doesn't assert accuracy here (that's eval/run_eval.py's job with a real
    # LLM) — just that the tool never crashes and always returns a valid
    # ClassifyOutput or a ToolError, across every fixture including the
    # deliberately awkward ones.
    for email, _expected in load_fixtures_with_labels():
        result = classify_email(ClassifyInput(subject=email.subject, body=email.body), llm=fake_llm)
        assert isinstance(result, (ClassifyOutput, ToolError)), f"bad type for {email.id}"


# ---------------------------------------------------------------------------
# extract_customer_info
# ---------------------------------------------------------------------------

def test_extract_customer_info_returns_valid_output(fake_llm):
    result = extract_customer_info(
        ExtractInput(
            subject="Order issue",
            body="My order #A-8823 hasn't shipped. Thanks, Kevin Wu",
        ),
        llm=fake_llm,
    )
    assert isinstance(result, ExtractOutput)


# ---------------------------------------------------------------------------
# search_knowledge_base
# ---------------------------------------------------------------------------

def test_search_knowledge_base_finds_relevant_article():
    result = search_knowledge_base(KBSearchInput(query="how do I reset my password"))
    assert isinstance(result, KBSearchOutput)
    assert len(result.hits) > 0
    assert any(hit.article_id == "kb_001" for hit in result.hits)


def test_search_knowledge_base_no_match_returns_empty():
    result = search_knowledge_base(KBSearchInput(query="xyzabc nonsense query qqq"))
    assert isinstance(result, KBSearchOutput)
    assert result.hits == []


# ---------------------------------------------------------------------------
# draft_reply
# ---------------------------------------------------------------------------

def test_draft_reply_returns_valid_output(fake_llm):
    kb_result = search_knowledge_base(KBSearchInput(query="reset password"))
    result = draft_reply(
        DraftReplyInput(
            subject="Password reset",
            body="I can't log in",
            category="how_to",
            customer_name="Kevin",
            kb_context=kb_result.hits,
        ),
        llm=fake_llm,
    )
    assert isinstance(result, DraftReplyOutput)
    assert len(result.draft_text) > 10


# ---------------------------------------------------------------------------
# log_to_sheet
# ---------------------------------------------------------------------------

def test_log_to_sheet_appends_row(tmp_path, monkeypatch):
    fake_path = tmp_path / "sheet_log.csv"
    monkeypatch.setattr("agent.tools.sheets.LOCAL_LOG_PATH", fake_path)

    result = log_to_sheet(LogToSheetInput(
        email_id="em_test", sender="a@b.com", category="billing",
        urgency="high", action_taken="escalated",
    ))
    assert isinstance(result, LogToSheetOutput)
    assert result.success is True
    assert result.destination == "local_csv"
    assert fake_path.exists()

    with open(fake_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["email_id"] == "em_test"


def test_log_to_sheet_uses_google_sheets_when_configured(monkeypatch):
    append_calls = []

    class _FakeValues:
        def append(self, **kwargs):
            append_calls.append(kwargs)
            return type("Exec", (), {"execute": lambda self: {}})()

    class _FakeSpreadsheets:
        def values(self):
            return _FakeValues()

    class _FakeSheetsService:
        def spreadsheets(self):
            return _FakeSpreadsheets()

    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setattr("agent.tools.sheets.google_auth.is_configured", lambda: True)
    monkeypatch.setattr("agent.tools.sheets.google_auth.get_credentials", lambda: object())
    monkeypatch.setattr("agent.tools.sheets.build", lambda *a, **kw: _FakeSheetsService())

    result = log_to_sheet(LogToSheetInput(
        email_id="em_test", sender="a@b.com", category="billing",
        urgency="high", action_taken="escalated",
    ))

    assert isinstance(result, LogToSheetOutput)
    assert result.success is True
    assert result.destination == "google_sheets"
    assert len(append_calls) == 1
    assert append_calls[0]["spreadsheetId"] == "sheet-123"
    values_row = append_calls[0]["body"]["values"][0]
    assert values_row[2] == "em_test"  # email_id column, per _FIELDNAMES order


def test_log_to_sheet_google_sheets_failure_returns_tool_error(monkeypatch):
    class _FakeSheetsService:
        def spreadsheets(self):
            raise RuntimeError("Sheets API unavailable")

    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setattr("agent.tools.sheets.google_auth.is_configured", lambda: True)
    monkeypatch.setattr("agent.tools.sheets.google_auth.get_credentials", lambda: object())
    monkeypatch.setattr("agent.tools.sheets.build", lambda *a, **kw: _FakeSheetsService())

    result = log_to_sheet(LogToSheetInput(
        email_id="em_test", sender="a@b.com", category="billing",
        urgency="high", action_taken="escalated",
    ))
    assert isinstance(result, ToolError)
    assert result.tool == "log_to_sheet"


# ---------------------------------------------------------------------------
# escalate_to_human
# ---------------------------------------------------------------------------

def test_escalate_to_human_returns_valid_output():
    result = escalate_to_human(EscalateInput(email_id="em_test", reason="low confidence classification", priority="medium"))
    assert isinstance(result, EscalateOutput)
    assert result.escalated is True


def test_escalate_to_human_rejects_empty_reason():
    result = escalate_to_human(EscalateInput(email_id="em_test", reason="   "))
    assert isinstance(result, ToolError)


# ---------------------------------------------------------------------------
# Fixture loader sanity checks (Phase 1 checkpoint)
# ---------------------------------------------------------------------------

def test_fixture_loader_loads_50_emails_without_leaking_labels():
    emails = load_fixtures()
    assert len(emails) == 50
    for email in emails:
        assert not hasattr(email, "expected")


def test_fixture_labels_have_valid_categories():
    valid_categories = {"bug_report", "billing", "how_to", "sales", "spam", "other"}
    valid_urgencies = {"low", "medium", "high"}
    pairs = load_fixtures_with_labels()
    assert len(pairs) == 50
    for email, expected in pairs:
        assert expected["category"] in valid_categories, f"{email.id} bad category"
        assert expected["urgency"] in valid_urgencies, f"{email.id} bad urgency"
        assert isinstance(expected["should_escalate"], bool)
