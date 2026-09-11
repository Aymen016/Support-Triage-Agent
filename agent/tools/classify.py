from __future__ import annotations

import json

from pydantic import ValidationError

from typing import Optional

from agent.llm_client import LLMClient
from agent.prompts import CLASSIFY_EXTRA_INSTRUCTIONS_HEADER, CLASSIFY_SYSTEM
from agent.schemas import ClassifyInput, ClassifyOutput, ToolError


def classify_email(input: ClassifyInput, llm: LLMClient, extra_instructions: Optional[str] = None) -> ClassifyOutput | ToolError:
    """
    Category + urgency + confidence for a single email.

    `extra_instructions` lets a non-engineer tune routing behavior from the
    Settings screen (e.g. "treat anything mentioning 'lawsuit' as high
    urgency billing") without touching code or the base prompt.

    Never raises. On any failure (LLM call, JSON parse, schema validation)
    returns a ToolError so the agent loop can decide what to do next
    (e.g. retry once, or fall back to escalate_to_human).
    """
    system = CLASSIFY_SYSTEM
    if extra_instructions:
        system += CLASSIFY_EXTRA_INSTRUCTIONS_HEADER + extra_instructions

    user_msg = f"Subject: {input.subject}\n\nBody:\n{input.body}"

    try:
        response = llm.complete_json(system=system, user=user_msg)
    except Exception as e:
        return ToolError(tool="classify_email", error_type="llm_error", message=str(e))

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        return ToolError(
            tool="classify_email", error_type="llm_error",
            message=f"Model did not return valid JSON: {e}", raw_output=response.text,
        )

    try:
        return ClassifyOutput.model_validate(parsed)
    except ValidationError as e:
        return ToolError(
            tool="classify_email", error_type="validation_error",
            message=str(e), raw_output=response.text,
        )
