from __future__ import annotations

import json

from pydantic import ValidationError

from agent.llm_client import LLMClient
from agent.prompts import DRAFT_SYSTEM
from agent.schemas import DraftReplyInput, DraftReplyOutput, ToolError


def draft_reply(input: DraftReplyInput, llm: LLMClient) -> DraftReplyOutput | ToolError:
    """Generates a reply draft, grounded in whatever KB hits were passed in."""
    kb_block = "\n".join(
        f"- [{hit.article_id}] {hit.title}: {hit.excerpt}" for hit in input.kb_context
    ) or "(no knowledge base articles matched this email)"

    user_msg = (
        f"Original email:\nSubject: {input.subject}\n\n{input.body}\n\n"
        f"Category: {input.category}\n"
        f"Customer name: {input.customer_name or 'unknown'}\n\n"
        f"Knowledge base context:\n{kb_block}\n\n"
        f"Tone instructions: {input.tone_instructions}"
    )

    try:
        response = llm.complete_json(system=DRAFT_SYSTEM, user=user_msg)
    except Exception as e:
        return ToolError(tool="draft_reply", error_type="llm_error", message=str(e))

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        return ToolError(
            tool="draft_reply", error_type="llm_error",
            message=f"Model did not return valid JSON: {e}", raw_output=response.text,
        )

    try:
        return DraftReplyOutput.model_validate(parsed)
    except ValidationError as e:
        return ToolError(
            tool="draft_reply", error_type="validation_error",
            message=str(e), raw_output=response.text,
        )
