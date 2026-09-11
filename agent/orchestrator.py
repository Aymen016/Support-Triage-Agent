"""
The orchestrator is the model that decides WHICH tool to call next — the
"AGENT LOOP" box in the architecture diagram. It's a different concern from
agent.llm_client.LLMClient (which individual tools use internally to do
their own work, e.g. classify_email calling the model to actually classify).

Orchestrator.next_turn() takes the running message history + tool defs and
returns the model's decision: one or more tool calls, or a final answer.
"""
from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolCallRequest:
    id: str
    name: str
    input: dict


@dataclass
class OrchestratorTurn:
    assistant_message: dict  # {"role": "assistant", "content": [...]} — append verbatim to history
    tool_calls: list[ToolCallRequest]
    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens" | ...
    final_text: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0


class Orchestrator(ABC):
    @abstractmethod
    def next_turn(self, messages: list[dict], tools: list[dict]) -> OrchestratorTurn:
        raise NotImplementedError


ORCHESTRATOR_SYSTEM_PROMPT = """You triage one support email at a time for a small business.

Call exactly ONE tool at a time and wait for its result before deciding the
next step. Do not call the same tool twice unless its previous result was an
error. A typical email goes: classify_email -> extract_customer_info ->
search_knowledge_base -> draft_reply. If you're ever unsure, or the email
doesn't fit that pattern (spam, a thread reply with nothing to do, multiple
unrelated issues), call escalate_to_human with a specific reason instead of
guessing. Note: if classify_email comes back with low confidence, the system
will escalate automatically — you don't need to double-check that yourself.
"""


class AnthropicOrchestrator(Orchestrator):
    def __init__(self, model: str = "claude-sonnet-5", api_key: Optional[str] = None):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError("pip install anthropic") from e
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("No ANTHROPIC_API_KEY set — see .env.example, or use ScriptedOrchestrator offline.")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

    def next_turn(self, messages: list[dict], tools: list[dict]) -> OrchestratorTurn:
        start = time.perf_counter()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=ORCHESTRATOR_SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )
        latency_ms = (time.perf_counter() - start) * 1000

        content = [block.model_dump() for block in resp.content]
        tool_calls = [
            ToolCallRequest(id=b["id"], name=b["name"], input=b.get("input", {}))
            for b in content if b["type"] == "tool_use"
        ]
        final_text = "".join(b["text"] for b in content if b["type"] == "text") or None

        return OrchestratorTurn(
            assistant_message={"role": "assistant", "content": content},
            tool_calls=tool_calls,
            stop_reason=resp.stop_reason,
            final_text=final_text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            latency_ms=latency_ms,
        )


class ScriptedOrchestrator(Orchestrator):
    """
    Deterministic, no API calls: classify -> extract -> search -> draft,
    then stops. Used for offline tests and for running all 50 fixtures
    through the loop for free (Phase 3 checkpoint). NOT a stand-in for real
    orchestration quality — swap in AnthropicOrchestrator for that.

    `script` can be overridden to test specific loop behaviors (chaos
    testing lives in tests/test_loop.py, not here).
    """

    DEFAULT_SCRIPT = [
        ("classify_email", {}),
        ("extract_customer_info", {}),
        ("search_knowledge_base", {"query": "__EMAIL_SUBJECT__", "top_k": 3}),
        ("draft_reply", {}),
    ]

    def __init__(self, script: Optional[list[tuple[str, dict]]] = None):
        self.script = script if script is not None else list(self.DEFAULT_SCRIPT)
        self._call_count = 0

    def next_turn(self, messages: list[dict], tools: list[dict]) -> OrchestratorTurn:
        if self._call_count >= len(self.script):
            return OrchestratorTurn(
                assistant_message={"role": "assistant", "content": [{"type": "text", "text": "Done."}]},
                tool_calls=[], stop_reason="end_turn", final_text="Done.",
            )

        name, args = self.script[self._call_count]
        # Loop substitutes __EMAIL_SUBJECT__ with the real subject before we get here
        # (see loop.py) — kept as a placeholder marker so the script stays declarative.
        self._call_count += 1
        call_id = f"scripted_call_{self._call_count}"
        return OrchestratorTurn(
            assistant_message={
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}],
            },
            tool_calls=[ToolCallRequest(id=call_id, name=name, input=args)],
            stop_reason="tool_use",
        )
