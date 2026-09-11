"""
Picks the real Anthropic-backed orchestrator+LLM if ANTHROPIC_API_KEY is set,
otherwise falls back to the offline Scripted+Fake pair so the API and UI are
fully demoable with zero setup. The API always reports which one it used
(see RunSummaryOut.used_fake_llm) — never silently pretend fake results are
real classification accuracy.

IMPORTANT: build_orchestrator() must be called ONCE PER EMAIL, not reused
across a batch. ScriptedOrchestrator tracks "which step of this
conversation am I on" via internal state that's only valid for a single
run_agent_loop() call — reusing one instance across multiple emails means
every email after the first sees an already-exhausted script and gets
force-escalated. build_llm(), by contrast, IS safe to reuse across a whole
batch (both LLMClient implementations are stateless per-call).
"""
from __future__ import annotations

import os
from typing import Callable

from agent.llm_client import AnthropicLLMClient, FakeLLMClient, LLMClient
from agent.orchestrator import AnthropicOrchestrator, Orchestrator, ScriptedOrchestrator
from agent.schemas import IncomingEmail
from ingest import gmail_client
from ingest.fixture_loader import load_fixtures
from integrations import google_auth


def build_llm() -> tuple[LLMClient, bool]:
    """Returns (llm, used_fake). Safe to build once and reuse across a batch."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicLLMClient(), False
        except RuntimeError:
            pass
    return FakeLLMClient(), True


def build_orchestrator(used_fake: bool) -> Orchestrator:
    """Returns a FRESH orchestrator — call this once per email, never reuse."""
    if used_fake:
        return ScriptedOrchestrator()
    return AnthropicOrchestrator()


def build_email_source() -> tuple[Callable[[], list[IncomingEmail]], bool]:
    """
    Returns (fetch_fn, used_gmail). Real Gmail if OAuth is configured,
    fixtures otherwise — mirrors build_llm()'s auto-detect shape. Unlike
    build_llm() (which silently falls back to fake when a key is simply
    absent), a Gmail fetch *failure* once configured should surface loudly
    to the caller rather than silently falling back to fixtures — see
    api/main.py::_new_emails.
    """
    if google_auth.is_configured():
        label = os.environ.get("GMAIL_LABEL_TO_POLL", gmail_client.DEFAULT_LABEL)
        return (lambda: gmail_client.fetch_new_emails(label)), True
    return load_fixtures, False
