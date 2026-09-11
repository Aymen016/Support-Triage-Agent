from __future__ import annotations

import json

from pydantic import ValidationError

from agent.llm_client import LLMClient
from agent.prompts import EXTRACT_SYSTEM
from agent.schemas import ExtractInput, ExtractOutput, ToolError


def extract_customer_info(input: ExtractInput, llm: LLMClient) -> ExtractOutput | ToolError:
    """Pulls name / order-account id / product / email out of the email body."""
    user_msg = f"Subject: {input.subject}\n\nBody:\n{input.body}"

    try:
        response = llm.complete_json(system=EXTRACT_SYSTEM, user=user_msg)
    except Exception as e:
        return ToolError(tool="extract_customer_info", error_type="llm_error", message=str(e))

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        return ToolError(
            tool="extract_customer_info", error_type="llm_error",
            message=f"Model did not return valid JSON: {e}", raw_output=response.text,
        )

    try:
        return ExtractOutput.model_validate(parsed)
    except ValidationError as e:
        return ToolError(
            tool="extract_customer_info", error_type="validation_error",
            message=str(e), raw_output=response.text,
        )
