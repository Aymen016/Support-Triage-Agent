from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ApproveRequest(BaseModel):
    approver: str
    edited_text: Optional[str] = None


class RejectRequest(BaseModel):
    approver: str
    reason: str


class EscalateRequest(BaseModel):
    reason: str


class ClassificationOut(BaseModel):
    category: str
    urgency: str
    confidence: float
    reasoning: str


class DraftOut(BaseModel):
    draft_text: str
    edited_text: Optional[str]
    final_text: str
    sources_used: list[str]
    status: str
    approver: Optional[str]
    decided_at: Optional[datetime]


class EscalationOut(BaseModel):
    reason: str
    priority: str
    resolved: bool


class AgentStepOut(BaseModel):
    step_number: int
    tool_called: str
    arguments: dict
    result: dict
    is_error: bool
    latency_ms: float
    input_tokens: Optional[int]
    output_tokens: Optional[int]


class EmailSummaryOut(BaseModel):
    id: str
    from_address: str
    subject: str
    status: str
    created_at: datetime
    category: Optional[str] = None
    urgency: Optional[str] = None
    confidence: Optional[float] = None


class EmailDetailOut(BaseModel):
    id: str
    from_address: str
    subject: str
    body: str
    thread_id: Optional[str]
    status: str
    created_at: datetime
    classification: Optional[ClassificationOut]
    draft: Optional[DraftOut]
    escalation: Optional[EscalationOut]
    steps: list[AgentStepOut]


class SettingsOut(BaseModel):
    confidence_threshold: float
    auto_send_enabled: bool
    tone_instructions: str
    category_notes: str


class SettingsUpdate(BaseModel):
    confidence_threshold: Optional[float] = None
    auto_send_enabled: Optional[bool] = None
    tone_instructions: Optional[str] = None
    category_notes: Optional[str] = None


class RunSummaryOut(BaseModel):
    processed: int
    drafted: int
    escalated: int
    skipped_already_seen: int
    used_fake_llm: bool
    email_source: Literal["fixtures", "gmail"]


class IntegrationsStatusOut(BaseModel):
    gmail_connected: bool
    sheets_connected: bool
    ai_mode: Literal["claude", "fake"]
