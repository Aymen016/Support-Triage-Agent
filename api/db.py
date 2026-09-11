"""
PHASE 4 — persistence + the human-in-the-loop gate.

Every email, classification, draft, and agent step gets a row (per the
plan). The core rule this file exists to enforce: **nothing gets marked
sent except through approve_email() — the loop itself never sends
anything, it only ever gets to `status="pending"`.**

sqlite for dev (see DATABASE_URL in .env.example) — swap the URL for
Postgres later; nothing else here is sqlite-specific.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from agent.schemas import IncomingEmail, LoopResult
from agent.schemas import EscalateInput, LogToSheetInput
from agent.tools.escalate import escalate_to_human
from agent.tools.sheets import log_to_sheet
from ingest import gmail_client
from integrations import google_auth


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmailRow(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    from_address: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String)
    thread_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # "fixture" | "gmail" — gates whether approve_email() may attempt a real send.
    source: Mapped[str] = mapped_column(String, default="fixture")
    # pending | approved | escalated | rejected
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    classification: Mapped[Optional["ClassificationRow"]] = relationship(back_populates="email", uselist=False, cascade="all, delete-orphan")
    draft: Mapped[Optional["DraftRow"]] = relationship(back_populates="email", uselist=False, cascade="all, delete-orphan")
    escalation: Mapped[Optional["EscalationRow"]] = relationship(back_populates="email", uselist=False, cascade="all, delete-orphan")
    steps: Mapped[list["AgentStepRow"]] = relationship(back_populates="email", cascade="all, delete-orphan", order_by="AgentStepRow.step_number")


class ClassificationRow(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.id"))
    category: Mapped[str] = mapped_column(String)
    urgency: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(String)

    email: Mapped["EmailRow"] = relationship(back_populates="classification")


class DraftRow(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.id"))
    draft_text: Mapped[str] = mapped_column(String)
    edited_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sources_used: Mapped[list] = mapped_column(JSON, default=list)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String, default="pending")
    approver: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    email: Mapped["EmailRow"] = relationship(back_populates="draft")

    @property
    def final_text(self) -> str:
        return self.edited_text if self.edited_text is not None else self.draft_text


class EscalationRow(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.id"))
    reason: Mapped[str] = mapped_column(String)
    priority: Mapped[str] = mapped_column(String)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    email: Mapped["EmailRow"] = relationship(back_populates="escalation")


class SettingsRow(Base):
    """
    Singleton row (id always 1). Backs the Settings screen. confidence_threshold
    and tone_instructions genuinely change agent behavior on the next /run —
    see api/main.py. category_notes get appended to the classify prompt so a
    non-engineer can tune routing without touching code. auto_send_enabled is
    stored but NOT acted on yet — there's no real send channel until Phase 6's
    Gmail integration exists, and pretending to "send" without one would be
    misleading in a client demo.
    """
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    auto_send_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tone_instructions: Mapped[str] = mapped_column(
        String, default="Friendly, concise, professional. Sign off as 'The Support Team'."
    )
    category_notes: Mapped[str] = mapped_column(String, default="")


def get_settings(session: Session) -> SettingsRow:
    row = session.get(SettingsRow, 1)
    if row is None:
        row = SettingsRow(id=1)
        session.add(row)
        session.flush()
    return row


def update_settings(session: Session, **kwargs) -> SettingsRow:
    row = get_settings(session)
    for key, value in kwargs.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    session.flush()
    return row


class AgentStepRow(Base):
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(ForeignKey("emails.id"))
    step_number: Mapped[int] = mapped_column(Integer)
    tool_called: Mapped[str] = mapped_column(String)
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    email: Mapped["EmailRow"] = relationship(back_populates="steps")


# ---------------------------------------------------------------------------
# Engine / session
# ---------------------------------------------------------------------------

_DEFAULT_URL = "sqlite:///./data/triage.db"


def get_engine(database_url: Optional[str] = None):
    url = database_url or os.environ.get("DATABASE_URL", _DEFAULT_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker):
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def save_incoming_email(session: Session, email: IncomingEmail) -> EmailRow:
    existing = session.get(EmailRow, email.id)
    if existing:
        return existing
    row = EmailRow(
        id=email.id, from_address=email.from_address, subject=email.subject,
        body=email.body, thread_id=email.thread_id, received_at=email.received_at,
        source=email.source, status="pending",
    )
    session.add(row)
    session.flush()
    return row


def save_loop_result(session: Session, email: IncomingEmail, result: LoopResult) -> EmailRow:
    """
    Persists everything a completed agent run produced: the email itself,
    its classification (if any), every audit step, and either a pending
    draft or an escalation. Never marks anything "approved" or "sent" —
    that only happens through approve_email() below.
    """
    email_row = save_incoming_email(session, email)
    email_row.status = "escalated" if result.status == "escalated" else "pending"

    if result.classify:
        session.add(ClassificationRow(
            email_id=email.id, category=result.classify.category, urgency=result.classify.urgency,
            confidence=result.classify.confidence, reasoning=result.classify.reasoning,
        ))

    for step in result.steps:
        session.add(AgentStepRow(
            email_id=email.id, step_number=step.step_number, tool_called=step.tool_called,
            arguments=step.arguments, result=step.result, is_error=step.is_error,
            latency_ms=step.latency_ms, input_tokens=step.input_tokens, output_tokens=step.output_tokens,
        ))

    if result.status == "drafted" and result.draft:
        session.add(DraftRow(
            email_id=email.id, draft_text=result.draft.draft_text,
            sources_used=result.draft.sources_used, status="pending",
        ))
    elif result.status == "escalated" and result.escalate:
        session.add(EscalationRow(email_id=email.id, reason=result.escalate.reason, priority=result.escalate.priority))

    session.flush()
    return email_row


# ---------------------------------------------------------------------------
# The human-in-the-loop gate: the only path to "sent"
# ---------------------------------------------------------------------------

class GateError(Exception):
    pass


class SendError(GateError):
    """Raised when a real Gmail send fails during approval — the draft stays
    'pending' (approval did not happen), since marking it approved while
    nothing was actually sent would violate the one send-path invariant."""
    pass


def approve_email(session: Session, email_id: str, approver: str, edited_text: Optional[str] = None) -> EmailRow:
    """Approve (optionally with edits) -> logs to sheet as approved_sent. THE only send path.

    For a Gmail-sourced email with Gmail configured, this also sends the
    real reply before marking anything approved — if the send fails, the
    draft stays 'pending' and a SendError is raised (see SendError). Fixture-
    sourced emails, or when Gmail isn't configured, skip the send entirely."""
    email_row = session.get(EmailRow, email_id)
    if email_row is None:
        raise GateError(f"no such email: {email_id}")
    if email_row.draft is None:
        raise GateError(f"email {email_id} has no draft to approve (was it escalated instead?)")
    if email_row.draft.status != "pending":
        raise GateError(f"draft for {email_id} is already {email_row.draft.status}")

    final_text = edited_text if edited_text else email_row.draft.draft_text

    if email_row.source == "gmail" and google_auth.is_configured():
        try:
            gmail_client.send_reply(
                original_message_id=email_row.id, thread_id=email_row.thread_id,
                to_address=email_row.from_address, subject=f"Re: {email_row.subject}",
                body_text=final_text,
            )
        except Exception as e:
            raise SendError(f"approval not recorded — Gmail send failed: {e}")

    if edited_text:
        email_row.draft.edited_text = edited_text
    email_row.draft.status = "approved"
    email_row.draft.approver = approver
    email_row.draft.decided_at = _now()
    email_row.status = "approved"

    classification = email_row.classification
    log_to_sheet(LogToSheetInput(
        email_id=email_id, sender=email_row.from_address,
        category=classification.category if classification else "other",
        urgency=classification.urgency if classification else "medium",
        action_taken="approved_sent", approver=approver,
    ))
    session.flush()
    return email_row


def reject_email(session: Session, email_id: str, approver: str, reason: str) -> EmailRow:
    """Rejections get stored — this is the improvement dataset (Stretch Goals)."""
    email_row = session.get(EmailRow, email_id)
    if email_row is None:
        raise GateError(f"no such email: {email_id}")
    if email_row.draft is None:
        raise GateError(f"email {email_id} has no draft to reject")

    email_row.draft.status = "rejected"
    email_row.draft.approver = approver
    email_row.draft.decided_at = _now()
    email_row.status = "rejected"

    classification = email_row.classification
    log_to_sheet(LogToSheetInput(
        email_id=email_id, sender=email_row.from_address,
        category=classification.category if classification else "other",
        urgency=classification.urgency if classification else "medium",
        action_taken="rejected", approver=approver,
    ))
    session.flush()
    return email_row


def escalate_email_manually(session: Session, email_id: str, reason: str) -> EmailRow:
    """A human (or the review UI) can escalate an email the agent had drafted."""
    email_row = session.get(EmailRow, email_id)
    if email_row is None:
        raise GateError(f"no such email: {email_id}")

    result = escalate_to_human(EscalateInput(email_id=email_id, reason=reason, priority="medium"))
    session.add(EscalationRow(email_id=email_id, reason=result.reason, priority=result.priority))
    email_row.status = "escalated"
    if email_row.draft:
        email_row.draft.status = "rejected"  # superseded by the escalation
    session.flush()
    return email_row


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_emails(session: Session, status: Optional[str] = None) -> list[EmailRow]:
    stmt = select(EmailRow).order_by(EmailRow.created_at.desc())
    if status:
        stmt = stmt.where(EmailRow.status == status)
    return list(session.scalars(stmt))


def get_email(session: Session, email_id: str) -> Optional[EmailRow]:
    return session.get(EmailRow, email_id)
