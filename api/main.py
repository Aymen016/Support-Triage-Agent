"""
PHASE 5 backend. Run: uvicorn api.main:app --reload
Docs at http://localhost:8000/docs

Routes:
  GET  /health
  GET  /emails?status=pending           list the review queue, optionally filtered
  GET  /emails/{email_id}               full detail: classification, draft, steps
  POST /emails/{email_id}/approve       {approver, edited_text?}  -> THE send path
  POST /emails/{email_id}/reject        {approver, reason}
  POST /emails/{email_id}/escalate      {reason}                 -> manual escalate of a drafted email
  POST /run                             process new fixture emails, block until done
  GET  /run/stream                      same, but SSE — live step-by-step progress
  GET  /runs/{email_id}                 the step timeline alone (Screen 3)
  GET  /integrations/status             connection status for Gmail/Sheets/AI — frontend chrome only

Nothing here ever sends an email. approve_email() (api/db.py) is the single
gate everything else in this file routes through before anything is marked
"sent" — see the plan's Phase 4 note on why that's the most important design
decision in the project.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from agent.loop import run_agent_loop
from agent.schemas import AgentStep
from api.api_schemas import (
    AgentStepOut, ApproveRequest, ClassificationOut, DraftOut, EmailDetailOut,
    EmailSummaryOut, EscalateRequest, EscalationOut, IntegrationsStatusOut, RejectRequest,
    RunSummaryOut, SettingsOut, SettingsUpdate,
)
from api.db import (
    EmailRow, GateError, approve_email, escalate_email_manually, get_email, get_settings, init_db,
    list_emails, make_session_factory, reject_email, save_incoming_email, save_loop_result, session_scope,
    update_settings,
)
from api.pipeline import build_email_source, build_llm, build_orchestrator
from integrations import google_auth

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.db import get_engine
    engine = get_engine()
    init_db(engine)
    app.state.session_factory = make_session_factory(engine)
    yield


app = FastAPI(title="Support Triage Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session_factory():
    return app.state.session_factory


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/integrations/status", response_model=IntegrationsStatusOut)
def get_integrations_status():
    """Read-only connection status for the frontend's app shell — never
    used to gate behavior server-side, that's decided independently by
    api/pipeline.py and agent/tools/sheets.py at the moment each action runs."""
    gmail_connected = google_auth.is_configured()
    sheets_connected = gmail_connected and bool(os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID"))
    ai_mode = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "fake"
    return IntegrationsStatusOut(gmail_connected=gmail_connected, sheets_connected=sheets_connected, ai_mode=ai_mode)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _summary(row: EmailRow) -> EmailSummaryOut:
    c = row.classification
    return EmailSummaryOut(
        id=row.id, from_address=row.from_address, subject=row.subject, status=row.status,
        created_at=row.created_at,
        category=c.category if c else None, urgency=c.urgency if c else None,
        confidence=c.confidence if c else None,
    )


def _detail(row: EmailRow) -> EmailDetailOut:
    c = row.classification
    d = row.draft
    e = row.escalation
    return EmailDetailOut(
        id=row.id, from_address=row.from_address, subject=row.subject, body=row.body,
        thread_id=row.thread_id, status=row.status, created_at=row.created_at,
        classification=ClassificationOut(category=c.category, urgency=c.urgency, confidence=c.confidence, reasoning=c.reasoning) if c else None,
        draft=DraftOut(
            draft_text=d.draft_text, edited_text=d.edited_text, final_text=d.final_text,
            sources_used=d.sources_used, status=d.status, approver=d.approver, decided_at=d.decided_at,
        ) if d else None,
        escalation=EscalationOut(reason=e.reason, priority=e.priority, resolved=e.resolved) if e else None,
        steps=[
            AgentStepOut(
                step_number=s.step_number, tool_called=s.tool_called, arguments=s.arguments,
                result=s.result, is_error=s.is_error, latency_ms=s.latency_ms,
                input_tokens=s.input_tokens, output_tokens=s.output_tokens,
            ) for s in row.steps
        ],
    )


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@app.get("/emails", response_model=list[EmailSummaryOut])
def get_emails(status: Optional[str] = None, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        rows = list_emails(session, status=status)
        return [_summary(r) for r in rows]


@app.get("/emails/{email_id}", response_model=EmailDetailOut)
def get_email_detail(email_id: str, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        row = get_email(session, email_id)
        if row is None:
            raise HTTPException(404, f"no such email: {email_id}")
        return _detail(row)


@app.get("/runs/{email_id}", response_model=list[AgentStepOut])
def get_run_steps(email_id: str, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        row = get_email(session, email_id)
        if row is None:
            raise HTTPException(404, f"no such email: {email_id}")
        return [
            AgentStepOut(
                step_number=s.step_number, tool_called=s.tool_called, arguments=s.arguments,
                result=s.result, is_error=s.is_error, latency_ms=s.latency_ms,
                input_tokens=s.input_tokens, output_tokens=s.output_tokens,
            ) for s in row.steps
        ]


# ---------------------------------------------------------------------------
# The approval gate
# ---------------------------------------------------------------------------

@app.post("/emails/{email_id}/approve", response_model=EmailDetailOut)
def post_approve(email_id: str, body: ApproveRequest, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        try:
            approve_email(session, email_id, approver=body.approver, edited_text=body.edited_text)
        except GateError as e:
            raise HTTPException(400, str(e))
        return _detail(get_email(session, email_id))


@app.post("/emails/{email_id}/reject", response_model=EmailDetailOut)
def post_reject(email_id: str, body: RejectRequest, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        try:
            reject_email(session, email_id, approver=body.approver, reason=body.reason)
        except GateError as e:
            raise HTTPException(400, str(e))
        return _detail(get_email(session, email_id))


@app.post("/emails/{email_id}/escalate", response_model=EmailDetailOut)
def post_escalate(email_id: str, body: EscalateRequest, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        try:
            escalate_email_manually(session, email_id, reason=body.reason)
        except GateError as e:
            raise HTTPException(400, str(e))
        return _detail(get_email(session, email_id))


# ---------------------------------------------------------------------------
# Settings — "configurable by a non-engineer"
# ---------------------------------------------------------------------------

@app.get("/settings", response_model=SettingsOut)
def get_settings_route(session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        s = get_settings(session)
        return SettingsOut(
            confidence_threshold=s.confidence_threshold, auto_send_enabled=s.auto_send_enabled,
            tone_instructions=s.tone_instructions, category_notes=s.category_notes,
        )


@app.put("/settings", response_model=SettingsOut)
def put_settings_route(body: SettingsUpdate, session_factory=Depends(get_session_factory)):
    with session_scope(session_factory) as session:
        s = update_settings(session, **body.model_dump(exclude_unset=True))
        return SettingsOut(
            confidence_threshold=s.confidence_threshold, auto_send_enabled=s.auto_send_enabled,
            tone_instructions=s.tone_instructions, category_notes=s.category_notes,
        )


# ---------------------------------------------------------------------------
# Running the agent
# ---------------------------------------------------------------------------

def _new_emails(session_factory) -> tuple[list, bool, int]:
    """
    New emails not already in the DB — from Gmail if OAuth is configured,
    fixtures otherwise (see api/pipeline.py::build_email_source). Returns
    (to_process, used_gmail, total_candidates_fetched).

    A configured Gmail fetch that *fails* raises loudly (502) rather than
    silently falling back to fixtures — swapping data sources mid-demo
    would be far more confusing than an explicit error. This mirrors
    build_llm()'s auto-detect, except build_llm() intentionally falls back
    to fake when a key is simply absent (never require a key to demo).
    """
    fetch_fn, used_gmail = build_email_source()
    with session_scope(session_factory) as session:
        existing_ids = {row.id for row in list_emails(session)}
    try:
        candidates = fetch_fn()
    except Exception as e:
        source_name = "gmail" if used_gmail else "fixtures"
        raise HTTPException(502, f"failed to fetch new emails ({source_name}): {e}")
    to_process = [e for e in candidates if e.id not in existing_ids]
    return to_process, used_gmail, len(candidates)


@app.post("/run", response_model=RunSummaryOut)
def post_run(session_factory=Depends(get_session_factory)):
    llm, used_fake = build_llm()
    to_process, used_gmail, total_candidates = _new_emails(session_factory)

    with session_scope(session_factory) as session:
        settings = get_settings(session)
        confidence_threshold = settings.confidence_threshold
        tone_instructions = settings.tone_instructions
        category_notes = settings.category_notes or None

    drafted = escalated = 0
    for email in to_process:
        result = run_agent_loop(
            email, orchestrator=build_orchestrator(used_fake), llm=llm,
            confidence_threshold=confidence_threshold,
            classify_extra_instructions=category_notes,
            default_tone_instructions=tone_instructions,
        )
        with session_scope(session_factory) as session:
            save_loop_result(session, email, result)
        if result.status == "drafted":
            drafted += 1
        else:
            escalated += 1

    return RunSummaryOut(
        processed=len(to_process), drafted=drafted, escalated=escalated,
        skipped_already_seen=total_candidates - len(to_process), used_fake_llm=used_fake,
        email_source="gmail" if used_gmail else "fixtures",
    )


@app.get("/run/stream")
async def get_run_stream(session_factory=Depends(get_session_factory)):
    """
    Live progress via Server-Sent Events, for the 'agent working' indicator.
    Runs the (synchronous) loop in a background thread; each AgentStep gets
    pushed onto a queue and relayed to the client as it happens.
    """
    llm, used_fake = build_llm()
    to_process, used_gmail, _total_candidates = _new_emails(session_factory)
    with session_scope(session_factory) as session:
        settings = get_settings(session)
        confidence_threshold = settings.confidence_threshold
        tone_instructions = settings.tone_instructions
        category_notes = settings.category_notes or None
    event_queue: queue.Queue = queue.Queue()

    def worker():
        for email in to_process:
            event_queue.put(("email_start", {"email_id": email.id, "subject": email.subject}))

            def on_step(step: AgentStep, _email=email):
                event_queue.put(("step", {"email_id": _email.id, **step.model_dump()}))

            result = run_agent_loop(
                email, orchestrator=build_orchestrator(used_fake), llm=llm, on_step=on_step,
                confidence_threshold=confidence_threshold,
                classify_extra_instructions=category_notes,
                default_tone_instructions=tone_instructions,
            )
            with session_scope(session_factory) as session:
                save_loop_result(session, email, result)
            event_queue.put(("email_done", {"email_id": email.id, "status": result.status}))
        event_queue.put(("done", {
            "used_fake_llm": used_fake, "total": len(to_process),
            "email_source": "gmail" if used_gmail else "fixtures",
        }))

    threading.Thread(target=worker, daemon=True).start()

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            kind, payload = await loop.run_in_executor(None, event_queue.get)
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
            if kind == "done":
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")
