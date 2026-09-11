"""
Thin abstraction over "call an LLM and get JSON back".

Why this exists: every tool that needs a model (classify, extract, draft)
depends on this interface, not on the Anthropic SDK directly. That's what
makes Phase 2's checkpoint possible — "call every tool directly from a
Python REPL and get valid output" — without needing a live API key, and
it's what makes agent/loop.py's real tool-calling loop (Phase 3) swappable
to GPT-4-class models later without touching tool code.

Two implementations:
- AnthropicLLMClient: real calls to api.anthropic.com (needs ANTHROPIC_API_KEY)
- FakeLLMClient: deterministic canned/rule-based responses for tests and
  for running the whole pipeline offline against the fixtures
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str  # raw text content — callers parse JSON out of this themselves
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        """Ask the model to return a single JSON object as its entire response."""
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    def __init__(self, model: str = "claude-sonnet-5", api_key: Optional[str] = None):
        import time  # local import so `time` isn't a hard dep of the module namespace
        self._time = time
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "The 'anthropic' package is required for AnthropicLLMClient. "
                "pip install anthropic"
            ) from e
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "No ANTHROPIC_API_KEY set. Put it in your .env file (see .env.example) "
                "or pass api_key= explicitly. For offline dev/tests, use FakeLLMClient instead."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

    def complete_json(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        start = self._time.perf_counter()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system + "\n\nRespond with ONLY a single valid JSON object. No prose, no markdown fences.",
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = (self._time.perf_counter() - start) * 1000
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            latency_ms=latency_ms,
        )


class FakeLLMClient(LLMClient):
    """
    Deterministic, rule-based stand-in for the real model. Good enough to
    exercise every tool's plumbing (schema validation, error handling,
    audit logging) without spending money or needing network access.

    NOT a real classifier — swap in AnthropicLLMClient for real accuracy.
    Rules are intentionally simple keyword heuristics.
    """

    URGENT_WORDS = ["urgent", "down", "outage", "failed", "asap", "immediately", "furious", "unacceptable"]
    BILLING_WORDS = ["invoice", "charge", "refund", "billing", "payment", "subscription", "price"]
    HOWTO_WORDS = ["how do i", "how to", "reset", "password", "where is my", "where's my", "instructions"]
    SALES_WORDS = ["pricing", "quote", "demo", "enterprise plan", "interested in buying", "purchase order"]
    SPAM_WORDS = ["unsubscribe", "click here", "you've won", "limited time offer", "% off", "viagra"]

    def complete_json(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        text_lower = user.lower()

        if '"category"' in system and '"urgency"' in system:
            text = self._fake_classify(text_lower)
        elif '"customer_name"' in system:
            text = self._fake_extract(user)
        elif '"draft_text"' in system:
            text = self._fake_draft(user)
        else:
            text = "{}"

        return LLMResponse(text=text, input_tokens=len(user) // 4, output_tokens=len(text) // 4, latency_ms=5.0)

    def _fake_classify(self, text_lower: str) -> str:
        def hits(words):
            return sum(1 for w in words if w in text_lower)

        scores = {
            "spam": hits(self.SPAM_WORDS) * 2,
            "sales": hits(self.SALES_WORDS) * 2,
            "billing": hits(self.BILLING_WORDS) * 2,
            "how_to": hits(self.HOWTO_WORDS) * 2,
        }
        category = max(scores, key=scores.get) if max(scores.values()) > 0 else "bug_report"
        if all(v == 0 for v in scores.values()) and not any(w in text_lower for w in ["broken", "error", "bug", "not working", "issue", "problem"]):
            category = "other"

        urgency = "high" if hits(self.URGENT_WORDS) > 0 else ("low" if category in ("how_to", "spam") else "medium")
        confidence = 0.9 if max(scores.values()) >= 2 else 0.55

        return json.dumps({
            "category": category,
            "urgency": urgency,
            "confidence": confidence,
            "reasoning": f"[fake-llm] keyword-based heuristic matched category={category}, urgency signal={hits(self.URGENT_WORDS)}",
        })

    def _fake_extract(self, user: str) -> str:
        order_match = re.search(r"#?\s?(?:order|account|ticket)\s*#?\s*([A-Za-z0-9\-]{3,12})", user, re.IGNORECASE)
        name_match = re.search(r"(?:regards|thanks|best|sincerely|from)[,\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)?)", user)
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", user)
        return json.dumps({
            "customer_name": name_match.group(1) if name_match else None,
            "order_or_account_id": order_match.group(1) if order_match else None,
            "product_mentioned": None,
            "contact_email": email_match.group(0) if email_match else None,
        })

    def _fake_draft(self, user: str) -> str:
        return json.dumps({
            "draft_text": (
                "Hi there,\n\nThanks for reaching out — we've received your message and "
                "a member of our team is looking into it. We'll follow up shortly with next steps.\n\n"
                "The Support Team"
            ),
            "sources_used": [],
        })
