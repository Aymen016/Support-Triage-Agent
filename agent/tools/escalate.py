from __future__ import annotations

from agent.schemas import EscalateInput, EscalateOutput, ToolError


def escalate_to_human(input: EscalateInput) -> EscalateOutput | ToolError:
    """
    Deterministic — no LLM call needed. Flags an email for human review with
    a reason. The agent loop calls this directly when classify_email's
    confidence is below threshold, or the model chooses to call it itself
    when it's unsure what to do next.
    """
    if not input.reason.strip():
        return ToolError(
            tool="escalate_to_human", error_type="validation_error",
            message="An escalation without a reason isn't useful to the human reviewing it.",
        )
    return EscalateOutput(escalated=True, reason=input.reason, priority=input.priority)
