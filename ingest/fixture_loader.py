"""
Loads fixture emails as IncomingEmail objects. Ground-truth `expected`
labels are stripped before the email reaches the agent — the agent should
never see the answer key. Use load_fixtures_with_labels() in eval/run_eval.py
when you need both the email and its label.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.schemas import IncomingEmail

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixtures() -> list[IncomingEmail]:
    emails = []
    for path in sorted(FIXTURES_DIR.glob("em_*.json")):
        with open(path) as f:
            raw = json.load(f)
        raw = {k: v for k, v in raw.items() if k != "expected"}
        emails.append(IncomingEmail.model_validate(raw))
    return emails


def load_fixtures_with_labels() -> list[tuple[IncomingEmail, dict]]:
    pairs = []
    for path in sorted(FIXTURES_DIR.glob("em_*.json")):
        with open(path) as f:
            raw = json.load(f)
        expected = raw.get("expected", {})
        email_fields = {k: v for k, v in raw.items() if k != "expected"}
        pairs.append((IncomingEmail.model_validate(email_fields), expected))
    return pairs
