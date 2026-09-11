"""
The arguments the ORCHESTRATOR model actually has to supply for each tool.

Deliberately minimal. The loop already knows the current email's subject/body
and whatever earlier tools returned, so classify_email and
extract_customer_info take NO arguments from the model — asking the model to
retype the whole email into a tool call wastes tokens and risks transcription
errors. draft_reply pulls category/kb_context/customer_name from loop state
automatically; the model can only add an optional tone note. Only
search_knowledge_base and escalate_to_human need real judgment calls from the
model (what to search for; why to escalate), so those get real fields.

log_to_sheet is intentionally NOT here — per the architecture diagram, sheet
logging happens after human approval, not as a model-chosen action mid-loop.
The loop calls it directly and deterministically at the end of a run.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from agent.schemas import Urgency


class ClassifyCallArgs(BaseModel):
    pass


class ExtractCallArgs(BaseModel):
    pass


class SearchKBCallArgs(BaseModel):
    query: str = Field(description="What to search the knowledge base for.")
    top_k: int = Field(default=3, ge=1, le=5)


class DraftReplyCallArgs(BaseModel):
    tone_note: Optional[str] = Field(
        default=None,
        description="Optional extra tone guidance for this specific reply, e.g. 'customer is upset, be extra empathetic'.",
    )


class EscalateCallArgs(BaseModel):
    reason: str = Field(description="Why this needs a human, specifically.")
    priority: Urgency = "medium"


class ToolMeta(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    name: str
    description: str
    args_model: type[BaseModel]


TOOL_REGISTRY: dict[str, ToolMeta] = {
    "classify_email": ToolMeta(
        name="classify_email",
        description="Classify the current email into a category and urgency level. Call this first.",
        args_model=ClassifyCallArgs,
    ),
    "extract_customer_info": ToolMeta(
        name="extract_customer_info",
        description="Extract the customer's name, order/account ID, and product mentioned from the current email.",
        args_model=ExtractCallArgs,
    ),
    "search_knowledge_base": ToolMeta(
        name="search_knowledge_base",
        description="Search the support knowledge base for articles relevant to the customer's issue.",
        args_model=SearchKBCallArgs,
    ),
    "draft_reply": ToolMeta(
        name="draft_reply",
        description="Draft a reply to the customer. Call classify_email first — the draft needs a category.",
        args_model=DraftReplyCallArgs,
    ),
    "escalate_to_human": ToolMeta(
        name="escalate_to_human",
        description="Flag this email for human review instead of drafting a reply, with a specific reason.",
        args_model=EscalateCallArgs,
    ),
}


def anthropic_tool_defs() -> list[dict]:
    """Tool definitions in the shape Anthropic's `tools=` param expects."""
    defs = []
    for meta in TOOL_REGISTRY.values():
        schema = meta.args_model.model_json_schema()
        schema.pop("title", None)
        defs.append({"name": meta.name, "description": meta.description, "input_schema": schema})
    return defs
