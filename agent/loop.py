"""
PHASE 3 — the tool-calling loop.

1. Ask the orchestrator which tool to call next (or whether it's done).
2. Validate + execute that tool, using loop state to fill in arguments the
   model doesn't need to repeat (subject/body/category/kb_context).
3. Persist an AgentStep for every single execution (audit trail — Screen 3).
4. Repeat until a terminal state: a draft is produced, an escalation
   happens, or a safety cap forces one.

Design decisions (see README "Design decisions" for the fuller version):
- classify_email and extract_customer_info take no model-supplied
  arguments — the loop already knows the email being processed.
- If classify_email's confidence is below `confidence_threshold`, the loop
  force-escalates itself rather than asking the model whether to. The
  model's judgment about its own low-confidence call isn't trusted here.
- Two consecutive failures (bad tool name, invalid arguments, or a
  ToolError from the underlying function) on the same tool -> forced
  escalation. The model gets exactly one retry with the error message.
- A successful draft_reply or escalate_to_human ends the run immediately —
  we don't ask the model whether it wants to keep going once the goal
  state is reached.
- log_to_sheet is NOT a model-choosable tool (see agent/tool_specs.py) — the
  loop calls it directly and deterministically once a terminal state is
  reached, matching the architecture diagram.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from pydantic import ValidationError

from agent.orchestrator import Orchestrator, ToolCallRequest
from agent.llm_client import LLMClient
from agent.schemas import (
    AgentStep, ClassifyInput, ClassifyOutput, DraftReplyInput, EscalateInput,
    ExtractInput, IncomingEmail, KBArticleHit, KBSearchInput, LogToSheetInput,
    LoopResult, ToolError,
)
from agent.tool_specs import (
    DraftReplyCallArgs, EscalateCallArgs, SearchKBCallArgs, TOOL_REGISTRY, anthropic_tool_defs,
)
from agent.tools.classify import classify_email
from agent.tools.draft import draft_reply
from agent.tools.escalate import escalate_to_human
from agent.tools.extract import extract_customer_info
from agent.tools.knowledge_base import search_knowledge_base
from agent.tools.sheets import log_to_sheet

MAX_STEPS_DEFAULT = 8
CONFIDENCE_THRESHOLD_DEFAULT = 0.6

_ARGS_MODELS = {name: meta.args_model for name, meta in TOOL_REGISTRY.items()}


class _LoopState:
    def __init__(self, email: IncomingEmail, on_step: Optional[Callable[[AgentStep], None]] = None):
        self.email = email
        self.steps: list[AgentStep] = []
        self.classify: Optional[ClassifyOutput] = None
        self.extract = None
        self.kb_hits: list[KBArticleHit] = []
        self.draft = None
        self.escalate = None
        self.failures: dict[str, int] = {}
        self.status: Optional[str] = None  # "drafted" | "escalated", set on termination
        self.on_step = on_step


def _record(state: _LoopState, tool_called: str, arguments: dict, result_obj, latency_ms: float,
            is_error: bool, input_tokens: int = 0, output_tokens: int = 0) -> AgentStep:
    result_dict = result_obj.model_dump() if hasattr(result_obj, "model_dump") else {"detail": str(result_obj)}
    step = AgentStep(
        email_id=state.email.id,
        step_number=len(state.steps) + 1,
        tool_called=tool_called,
        arguments=arguments,
        result=result_dict,
        is_error=is_error,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    state.steps.append(step)
    if state.on_step:
        state.on_step(step)
    return step


def _force_escalate(state: _LoopState, reason: str) -> None:
    result = escalate_to_human(EscalateInput(email_id=state.email.id, reason=reason, priority="medium"))
    _record(state, "escalate_to_human", {"reason": reason, "priority": "medium", "forced": True}, result, 0.0,
            is_error=isinstance(result, ToolError))
    if not isinstance(result, ToolError):
        state.escalate = result
    state.status = "escalated"


def _tool_result_block(call_id: str, content: str, is_error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if is_error:
        block["is_error"] = True
    return block


DEFAULT_TONE_INSTRUCTIONS = "Friendly, concise, professional. Sign off as 'The Support Team'."


def _execute_tool(state: _LoopState, call: ToolCallRequest, llm: LLMClient,
                   confidence_threshold: float,
                   classify_extra_instructions: Optional[str] = None,
                   default_tone_instructions: str = DEFAULT_TONE_INSTRUCTIONS) -> tuple[dict, bool]:
    """Returns (tool_result_block, stop_requested)."""
    email = state.email

    if call.name not in TOOL_REGISTRY:
        available = ", ".join(TOOL_REGISTRY)
        _record(state, call.name, call.input, {"error": "unknown tool"}, 0.0, is_error=True)
        state.failures[call.name] = state.failures.get(call.name, 0) + 1
        msg = f"'{call.name}' is not a real tool. Available tools: {available}."
        if state.failures[call.name] >= 2:
            _force_escalate(state, f"model repeatedly called a nonexistent tool: '{call.name}'")
            return _tool_result_block(call.id, msg, is_error=True), True
        return _tool_result_block(call.id, msg, is_error=True), False

    args_model = _ARGS_MODELS[call.name]
    try:
        args = args_model.model_validate(call.input)
    except ValidationError as e:
        _record(state, call.name, call.input, {"error": str(e)}, 0.0, is_error=True)
        state.failures[call.name] = state.failures.get(call.name, 0) + 1
        if state.failures[call.name] >= 2:
            _force_escalate(state, f"'{call.name}' failed argument validation twice")
            return _tool_result_block(call.id, str(e), is_error=True), True
        return _tool_result_block(call.id, f"Invalid arguments: {e}", is_error=True), False

    start = time.perf_counter()

    if call.name == "classify_email":
        result = classify_email(
            ClassifyInput(subject=email.subject, body=email.body), llm=llm,
            extra_instructions=classify_extra_instructions,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        is_error = isinstance(result, ToolError)
        _record(state, call.name, args.model_dump(), result, latency_ms, is_error)
        if is_error:
            state.failures[call.name] = state.failures.get(call.name, 0) + 1
            if state.failures[call.name] >= 2:
                _force_escalate(state, "classify_email failed twice")
                return _tool_result_block(call.id, result.message, is_error=True), True
            return _tool_result_block(call.id, f"Tool error: {result.message}", is_error=True), False

        state.classify = result
        if result.confidence < confidence_threshold:
            _force_escalate(state, f"classification confidence {result.confidence:.2f} below threshold {confidence_threshold}")
            return _tool_result_block(call.id, result.model_dump_json()), True
        return _tool_result_block(call.id, result.model_dump_json()), False

    if call.name == "extract_customer_info":
        result = extract_customer_info(ExtractInput(subject=email.subject, body=email.body), llm=llm)
        latency_ms = (time.perf_counter() - start) * 1000
        is_error = isinstance(result, ToolError)
        _record(state, call.name, args.model_dump(), result, latency_ms, is_error)
        if is_error:
            return _tool_result_block(call.id, f"Tool error: {result.message}", is_error=True), False
        state.extract = result
        return _tool_result_block(call.id, result.model_dump_json()), False

    if call.name == "search_knowledge_base":
        assert isinstance(args, SearchKBCallArgs)
        query = args.query
        if query == "__EMAIL_SUBJECT__":  # ScriptedOrchestrator placeholder — see orchestrator.py
            query = f"{email.subject} {email.body}"
        result = search_knowledge_base(KBSearchInput(query=query, top_k=args.top_k))
        latency_ms = (time.perf_counter() - start) * 1000
        is_error = isinstance(result, ToolError)
        _record(state, call.name, {"query": query, "top_k": args.top_k}, result, latency_ms, is_error)
        if is_error:
            return _tool_result_block(call.id, f"Tool error: {result.message}", is_error=True), False
        state.kb_hits = result.hits
        return _tool_result_block(call.id, result.model_dump_json()), False

    if call.name == "draft_reply":
        assert isinstance(args, DraftReplyCallArgs)
        if state.classify is None:
            _record(state, call.name, args.model_dump(), {"error": "no classification yet"}, 0.0, is_error=True)
            return _tool_result_block(call.id, "Call classify_email before draft_reply.", is_error=True), False

        tone = default_tone_instructions
        if args.tone_note:
            tone += f" Additional guidance: {args.tone_note}"

        draft_input = DraftReplyInput(
            subject=email.subject, body=email.body, category=state.classify.category,
            customer_name=(state.extract.customer_name if state.extract else None),
            kb_context=state.kb_hits, tone_instructions=tone,
        )
        result = draft_reply(draft_input, llm=llm)
        latency_ms = (time.perf_counter() - start) * 1000
        is_error = isinstance(result, ToolError)
        _record(state, call.name, args.model_dump(), result, latency_ms, is_error)
        if is_error:
            state.failures[call.name] = state.failures.get(call.name, 0) + 1
            if state.failures[call.name] >= 2:
                _force_escalate(state, "draft_reply failed twice")
                return _tool_result_block(call.id, result.message, is_error=True), True
            return _tool_result_block(call.id, f"Tool error: {result.message}", is_error=True), False
        state.draft = result
        state.status = "drafted"
        return _tool_result_block(call.id, result.model_dump_json()), True

    if call.name == "escalate_to_human":
        assert isinstance(args, EscalateCallArgs)
        result = escalate_to_human(EscalateInput(email_id=email.id, reason=args.reason, priority=args.priority))
        latency_ms = (time.perf_counter() - start) * 1000
        is_error = isinstance(result, ToolError)
        _record(state, call.name, args.model_dump(), result, latency_ms, is_error)
        if not is_error:
            state.escalate = result
            state.status = "escalated"
            return _tool_result_block(call.id, result.model_dump_json()), True
        return _tool_result_block(call.id, f"Tool error: {result.message}", is_error=True), False

    raise AssertionError(f"unreachable — unhandled tool {call.name}")  # pragma: no cover


def run_agent_loop(
    email: IncomingEmail,
    orchestrator: Orchestrator,
    llm: LLMClient,
    confidence_threshold: float = CONFIDENCE_THRESHOLD_DEFAULT,
    max_steps: int = MAX_STEPS_DEFAULT,
    on_step: Optional[Callable[[AgentStep], None]] = None,
    classify_extra_instructions: Optional[str] = None,
    default_tone_instructions: str = DEFAULT_TONE_INSTRUCTIONS,
) -> LoopResult:
    state = _LoopState(email, on_step=on_step)
    tools = anthropic_tool_defs()
    messages = [{"role": "user", "content": f"Subject: {email.subject}\n\nBody:\n{email.body}"}]

    while len(state.steps) < max_steps and state.status is None:
        turn = orchestrator.next_turn(messages, tools)
        messages.append(turn.assistant_message)

        if not turn.tool_calls:
            # Model thinks it's done without drafting or escalating — don't trust that.
            _force_escalate(state, "agent ended the conversation without a draft or an escalation")
            break

        result_blocks = []
        stop = False
        for call in turn.tool_calls:
            if len(state.steps) >= max_steps:
                break
            block, stop_requested = _execute_tool(
                state, call, llm, confidence_threshold,
                classify_extra_instructions=classify_extra_instructions,
                default_tone_instructions=default_tone_instructions,
            )
            result_blocks.append(block)
            if stop_requested:
                stop = True
                break

        if stop or state.status is not None:
            break

        messages.append({"role": "user", "content": result_blocks})

    if state.status is None:
        _force_escalate(state, f"max steps ({max_steps}) exceeded without a decision")

    sheet_result = log_to_sheet(LogToSheetInput(
        email_id=email.id,
        sender=email.from_address,
        category=(state.classify.category if state.classify else "other"),
        urgency=(state.classify.urgency if state.classify else "medium"),
        action_taken=("escalated" if state.status == "escalated" else "drafted"),
    ))
    if isinstance(sheet_result, ToolError):
        sheet_result = None

    return LoopResult(
        email_id=email.id, status=state.status, steps=state.steps,
        classify=state.classify, extract=state.extract, kb_hits=state.kb_hits,
        draft=state.draft, escalate=state.escalate, sheet_log=sheet_result,
    )
