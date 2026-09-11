import pytest
from pydantic import ValidationError

from agent.schemas import ClassifyOutput, DraftReplyOutput, IncomingEmail


def test_classify_output_rejects_bad_category():
    with pytest.raises(ValidationError):
        ClassifyOutput(category="not_a_real_category", urgency="high", confidence=0.9, reasoning="test")


def test_classify_output_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        ClassifyOutput(category="spam", urgency="low", confidence=1.5, reasoning="test")


def test_classify_output_rejects_empty_reasoning():
    with pytest.raises(ValidationError):
        ClassifyOutput(category="spam", urgency="low", confidence=0.5, reasoning="   ")


def test_draft_reply_rejects_too_short_draft():
    with pytest.raises(ValidationError):
        DraftReplyOutput(draft_text="ok", sources_used=[])


def test_incoming_email_accepts_from_alias():
    # "from" is a reserved word in Python, schema uses alias="from"
    email = IncomingEmail.model_validate({
        "id": "em_test", "from": "a@b.com", "subject": "hi", "body": "hello"
    })
    assert email.from_address == "a@b.com"
