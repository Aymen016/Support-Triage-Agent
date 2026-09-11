import pytest

from agent.llm_client import FakeLLMClient
from agent.orchestrator import Orchestrator, OrchestratorTurn, ScriptedOrchestrator, ToolCallRequest
from agent.loop import run_agent_loop
from ingest.fixture_loader import load_fixtures


@pytest.fixture(autouse=True)
def _isolate_sheet_log(tmp_path, monkeypatch):
    # run_agent_loop always ends by calling log_to_sheet — without this, every
    # test here would append real rows to the repo's actual data/sheet_log.csv.
    monkeypatch.setattr("agent.tools.sheets.LOCAL_LOG_PATH", tmp_path / "sheet_log.csv")


# ---------------------------------------------------------------------------
# Phase 3 checkpoint: run all 50 fixtures through the loop end to end.
# Nothing crashes, everything produces either a draft or an escalation.
# ---------------------------------------------------------------------------

def test_all_50_fixtures_run_end_to_end():
    llm = FakeLLMClient()
    emails = load_fixtures()
    assert len(emails) == 50

    statuses = []
    for email in emails:
        result = run_agent_loop(email, orchestrator=ScriptedOrchestrator(), llm=llm)
        assert result.status in ("drafted", "escalated")
        assert len(result.steps) >= 1
        statuses.append(result.status)

    # sanity: not literally everything escalated (the scripted path should
    # reach draft_reply for most well-formed emails)
    assert statuses.count("drafted") > 0
    assert statuses.count("escalated") > 0


def test_happy_path_produces_a_draft_and_a_sheet_log():
    llm = FakeLLMClient()
    email = load_fixtures()[15]  # em_016 — how do I reset my password (routine, unambiguous)
    result = run_agent_loop(email, orchestrator=ScriptedOrchestrator(), llm=llm)

    assert result.status == "drafted"
    assert result.draft is not None
    assert result.classify is not None
    assert result.sheet_log is not None
    assert result.sheet_log.success is True
    # every step got persisted, in order
    assert [s.step_number for s in result.steps] == list(range(1, len(result.steps) + 1))


# ---------------------------------------------------------------------------
# Chaos testing: fake orchestrators that misbehave in the specific ways
# the project plan calls out.
# ---------------------------------------------------------------------------

class _HallucinatedToolOrchestrator(Orchestrator):
    """Always calls a tool name that doesn't exist."""
    def next_turn(self, messages, tools):
        return OrchestratorTurn(
            assistant_message={"role": "assistant", "content": [
                {"type": "tool_use", "id": "x1", "name": "send_email_directly", "input": {}}
            ]},
            tool_calls=[ToolCallRequest(id="x1", name="send_email_directly", input={})],
            stop_reason="tool_use",
        )


def test_hallucinated_tool_name_escalates_instead_of_crashing():
    llm = FakeLLMClient()
    email = load_fixtures()[0]
    result = run_agent_loop(email, orchestrator=_HallucinatedToolOrchestrator(), llm=llm)
    assert result.status == "escalated"
    assert any(s.tool_called == "escalate_to_human" for s in result.steps)


class _MalformedArgsOrchestrator(Orchestrator):
    """search_knowledge_base requires a `query` string — omit it every time."""
    def next_turn(self, messages, tools):
        return OrchestratorTurn(
            assistant_message={"role": "assistant", "content": [
                {"type": "tool_use", "id": "x1", "name": "search_knowledge_base", "input": {}}
            ]},
            tool_calls=[ToolCallRequest(id="x1", name="search_knowledge_base", input={})],
            stop_reason="tool_use",
        )


def test_malformed_arguments_retry_once_then_escalate():
    llm = FakeLLMClient()
    email = load_fixtures()[0]
    result = run_agent_loop(email, orchestrator=_MalformedArgsOrchestrator(), llm=llm)
    assert result.status == "escalated"
    error_steps = [s for s in result.steps if s.is_error]
    assert len(error_steps) >= 1


class _NeverEndsOrchestrator(Orchestrator):
    """Keeps calling extract_customer_info forever — must hit the step cap."""
    def next_turn(self, messages, tools):
        return OrchestratorTurn(
            assistant_message={"role": "assistant", "content": [
                {"type": "tool_use", "id": "xN", "name": "extract_customer_info", "input": {}}
            ]},
            tool_calls=[ToolCallRequest(id="xN", name="extract_customer_info", input={})],
            stop_reason="tool_use",
        )


def test_infinite_loop_hits_step_cap_and_escalates():
    llm = FakeLLMClient()
    email = load_fixtures()[0]
    result = run_agent_loop(email, orchestrator=_NeverEndsOrchestrator(), llm=llm, max_steps=8)
    assert result.status == "escalated"
    assert len(result.steps) <= 8 + 1  # +1 allows the forced escalate step itself
    assert any("max steps" in (s.arguments.get("reason") or "") for s in result.steps if s.tool_called == "escalate_to_human")


class _EndsImmediatelyOrchestrator(Orchestrator):
    """Model returns a final answer with no tool calls at all, on the first turn."""
    def next_turn(self, messages, tools):
        return OrchestratorTurn(
            assistant_message={"role": "assistant", "content": [{"type": "text", "text": "Looks fine, no action needed."}]},
            tool_calls=[], stop_reason="end_turn", final_text="Looks fine, no action needed.",
        )


def test_model_ending_without_a_decision_is_not_trusted():
    llm = FakeLLMClient()
    email = load_fixtures()[0]
    result = run_agent_loop(email, orchestrator=_EndsImmediatelyOrchestrator(), llm=llm)
    assert result.status == "escalated"


def test_low_confidence_classification_forces_escalation():
    class _LowConfidenceLLM(FakeLLMClient):
        def complete_json(self, system, user, max_tokens=1024):
            if '"category"' in system:
                import json
                return type(super().complete_json(system, user, max_tokens))(
                    text=json.dumps({"category": "other", "urgency": "low", "confidence": 0.2, "reasoning": "genuinely unclear"}),
                    input_tokens=10, output_tokens=10, latency_ms=1.0,
                )
            return super().complete_json(system, user, max_tokens)

    email = load_fixtures()[0]
    result = run_agent_loop(email, orchestrator=ScriptedOrchestrator(), llm=_LowConfidenceLLM(), confidence_threshold=0.6)
    assert result.status == "escalated"
    assert result.classify is not None and result.classify.confidence == 0.2
    reasons = [s.arguments.get("reason", "") for s in result.steps if s.tool_called == "escalate_to_human"]
    assert any("confidence" in r for r in reasons)
