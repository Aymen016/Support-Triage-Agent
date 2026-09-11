"""
Pydantic models for every tool's input/output, plus the core email + audit types.

Design rule (per project plan, Phase 2): every tool validates its own output
and returns a structured error rather than raising. That means agent/loop.py
never has to try/except a tool call for "did the LLM/tool return garbage" —
it just checks `isinstance(result, ToolError)`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, EmailStr, field_validator

Category = Literal["bug_report", "billing", "how_to", "sales", "spam", "other"]
Urgency = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Core email object (what ingest hands to the agent)
# ---------------------------------------------------------------------------

class IncomingEmail(BaseModel):
    id: str
    from_address: str = Field(alias="from")
    subject: str
    body: str
    thread_id: Optional[str] = None
    received_at: Optional[datetime] = None
    # "gmail" only for real Gmail-sourced emails — this is what lets
    # approve_email() (api/db.py) know a real send is safe to attempt.
    # Fixture JSON never carries this key, so old fixtures default correctly.
    source: Literal["fixture", "gmail"] = "fixture"

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Structured error — the thing every tool returns instead of raising
# ---------------------------------------------------------------------------

class ToolError(BaseModel):
    tool: str
    error_type: Literal["validation_error", "llm_error", "not_found", "external_api_error", "unknown"]
    message: str
    raw_output: Optional[str] = None  # what the LLM/tool actually returned, for debugging


# ---------------------------------------------------------------------------
# classify_email
# ---------------------------------------------------------------------------

class ClassifyInput(BaseModel):
    subject: str
    body: str


class ClassifyOutput(BaseModel):
    category: Category
    urgency: Urgency
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("reasoning")
    @classmethod
    def reasoning_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reasoning must not be empty — needed for the audit trail")
        return v


# ---------------------------------------------------------------------------
# extract_customer_info
# ---------------------------------------------------------------------------

class ExtractInput(BaseModel):
    subject: str
    body: str


class ExtractOutput(BaseModel):
    customer_name: Optional[str] = None
    order_or_account_id: Optional[str] = None
    product_mentioned: Optional[str] = None
    contact_email: Optional[str] = None  # not validated as EmailStr — bodies are messy free text


# ---------------------------------------------------------------------------
# search_knowledge_base
# ---------------------------------------------------------------------------

class KBSearchInput(BaseModel):
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class KBArticleHit(BaseModel):
    article_id: str
    title: str
    excerpt: str
    score: float = Field(ge=0.0, le=1.0)


class KBSearchOutput(BaseModel):
    hits: list[KBArticleHit]


# ---------------------------------------------------------------------------
# draft_reply
# ---------------------------------------------------------------------------

class DraftReplyInput(BaseModel):
    subject: str
    body: str
    category: Category
    customer_name: Optional[str] = None
    kb_context: list[KBArticleHit] = Field(default_factory=list)
    tone_instructions: str = "Friendly, concise, professional. Sign off as 'The Support Team'."


class DraftReplyOutput(BaseModel):
    draft_text: str
    sources_used: list[str] = Field(default_factory=list)  # article_ids from kb_context actually cited

    @field_validator("draft_text")
    @classmethod
    def draft_not_empty(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("draft_text is suspiciously short")
        return v


# ---------------------------------------------------------------------------
# log_to_sheet
# ---------------------------------------------------------------------------

class LogToSheetInput(BaseModel):
    email_id: str
    sender: str
    category: Category
    urgency: Urgency
    action_taken: Literal["drafted", "escalated", "approved_sent", "rejected"]
    approver: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LogToSheetOutput(BaseModel):
    success: bool
    sheet_row_id: Optional[str] = None
    destination: Literal["local_csv", "google_sheets"] = "local_csv"


# ---------------------------------------------------------------------------
# escalate_to_human
# ---------------------------------------------------------------------------

class EscalateInput(BaseModel):
    email_id: str
    reason: str
    priority: Urgency = "medium"


class EscalateOutput(BaseModel):
    escalated: bool
    reason: str
    priority: Urgency


# ---------------------------------------------------------------------------
# Audit log row (Phase 3 persists one of these per agent step)
# ---------------------------------------------------------------------------

class AgentStep(BaseModel):
    email_id: str
    step_number: int
    tool_called: str
    arguments: dict
    result: dict
    is_error: bool = False
    latency_ms: float
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


# ---------------------------------------------------------------------------
# Agent loop result (Phase 3)
# ---------------------------------------------------------------------------

class LoopResult(BaseModel):
    email_id: str
    status: Literal["drafted", "escalated"]
    steps: list[AgentStep]
    classify: Optional[ClassifyOutput] = None
    extract: Optional[ExtractOutput] = None
    kb_hits: list[KBArticleHit] = Field(default_factory=list)
    draft: Optional[DraftReplyOutput] = None
    escalate: Optional[EscalateOutput] = None
    sheet_log: Optional[LogToSheetOutput] = None

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum((s.input_tokens or 0) + (s.output_tokens or 0) for s in self.steps)
