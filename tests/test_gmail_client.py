import base64
import json
from email import message_from_bytes
from pathlib import Path

import pytest

from ingest import gmail_client

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "gmail_api"


def _load(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# _parse_message / _extract_body — pure functions, no auth/network
# ---------------------------------------------------------------------------

def test_parse_plain_text_message():
    raw = _load("plain_message.json")
    email = gmail_client._parse_message(raw)

    assert email.id == "msg_plain_1"
    assert email.from_address == "jane@example.com"
    assert email.subject == "Cannot reset my password"
    assert "forgot my password" in email.body
    assert email.thread_id == "thread_1"
    assert email.source == "gmail"
    assert email.received_at is not None


def test_parse_multipart_prefers_plain_text_over_html():
    raw = _load("multipart_alternative.json")
    email = gmail_client._parse_message(raw)

    assert "forgot my password" in email.body
    assert "<p>" not in email.body  # picked the plain part, not html


def test_parse_html_only_message_falls_back_and_strips_tags():
    raw = _load("html_only.json")
    email = gmail_client._parse_message(raw)

    assert "<p>" not in email.body
    assert "forgot my password" in email.body


def test_parse_message_with_no_from_header_defaults_gracefully():
    raw = {
        "id": "msg_no_from",
        "threadId": "thread_x",
        "payload": {"headers": [{"name": "Subject", "value": "Hi"}], "mimeType": "text/plain", "body": {}},
    }
    email = gmail_client._parse_message(raw)
    assert email.from_address == "unknown@unknown"
    assert email.body == ""


# ---------------------------------------------------------------------------
# fetch_new_emails / send_reply — mocked googleapiclient, no real network
# ---------------------------------------------------------------------------

class _FakeExecutable:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeMessages:
    def __init__(self, service):
        self._service = service

    def list(self, **kwargs):
        self._service.list_calls.append(kwargs)
        return _FakeExecutable({"messages": [{"id": mid} for mid in self._service.message_ids]})

    def get(self, **kwargs):
        self._service.get_calls.append(kwargs)
        return _FakeExecutable(self._service.messages_by_id[kwargs["id"]])

    def modify(self, **kwargs):
        self._service.modify_calls.append(kwargs)
        return _FakeExecutable({})

    def send(self, **kwargs):
        self._service.send_calls.append(kwargs)
        return _FakeExecutable({"id": "sent-1"})


class _FakeLabels:
    def __init__(self, service):
        self._service = service

    def list(self, **kwargs):
        return _FakeExecutable({"labels": self._service.labels})


class _FakeUsers:
    def __init__(self, service):
        self._service = service

    def messages(self):
        return _FakeMessages(self._service)

    def labels(self):
        return _FakeLabels(self._service)


class FakeGmailService:
    def __init__(self, message_ids, messages_by_id, labels):
        self.message_ids = message_ids
        self.messages_by_id = messages_by_id
        self.labels = labels
        self.list_calls = []
        self.get_calls = []
        self.modify_calls = []
        self.send_calls = []

    def users(self):
        return _FakeUsers(self)


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    monkeypatch.setattr(gmail_client.google_auth, "get_credentials", lambda: object())


def test_fetch_new_emails_parses_and_marks_processed(monkeypatch):
    plain = _load("plain_message.json")
    service = FakeGmailService(
        message_ids=[plain["id"]],
        messages_by_id={plain["id"]: plain},
        labels=[{"id": "Label_42", "name": "support"}],
    )
    monkeypatch.setattr(gmail_client, "build", lambda *a, **kw: service)

    emails = gmail_client.fetch_new_emails("support")

    assert len(emails) == 1
    assert emails[0].id == "msg_plain_1"
    assert emails[0].source == "gmail"
    # label swap happened for the fetched message
    assert len(service.modify_calls) == 1
    assert service.modify_calls[0]["id"] == "msg_plain_1"
    assert service.modify_calls[0]["body"] == {"removeLabelIds": ["Label_42"]}
    # listed under the resolved label id
    assert service.list_calls[0]["labelIds"] == ["Label_42"]


def test_fetch_new_emails_raises_when_label_missing(monkeypatch):
    service = FakeGmailService(message_ids=[], messages_by_id={}, labels=[{"id": "Label_1", "name": "other"}])
    monkeypatch.setattr(gmail_client, "build", lambda *a, **kw: service)

    with pytest.raises(ValueError, match="support"):
        gmail_client.fetch_new_emails("support")


def test_send_reply_threads_correctly(monkeypatch):
    service = FakeGmailService(
        message_ids=[],
        messages_by_id={
            "orig_1": {
                "id": "orig_1",
                "payload": {"headers": [{"name": "Message-ID", "value": "<rfc-id-123@example.com>"}]},
            }
        },
        labels=[],
    )
    monkeypatch.setattr(gmail_client, "build", lambda *a, **kw: service)

    gmail_client.send_reply(
        original_message_id="orig_1", thread_id="thread_1",
        to_address="jane@example.com", subject="Cannot reset my password",
        body_text="Here's how to reset your password...",
    )

    assert len(service.send_calls) == 1
    sent = service.send_calls[0]["body"]
    assert sent["threadId"] == "thread_1"

    mime = message_from_bytes(base64.urlsafe_b64decode(sent["raw"]))
    assert mime["To"] == "jane@example.com"
    assert mime["Subject"] == "Re: Cannot reset my password"
    assert mime["In-Reply-To"] == "<rfc-id-123@example.com>"
    assert mime["References"] == "<rfc-id-123@example.com>"


def test_send_reply_does_not_double_prefix_subject(monkeypatch):
    service = FakeGmailService(
        message_ids=[],
        messages_by_id={"orig_1": {"id": "orig_1", "payload": {"headers": []}}},
        labels=[],
    )
    monkeypatch.setattr(gmail_client, "build", lambda *a, **kw: service)

    gmail_client.send_reply(
        original_message_id="orig_1", thread_id=None,
        to_address="jane@example.com", subject="Re: Already prefixed",
        body_text="body",
    )

    mime = message_from_bytes(base64.urlsafe_b64decode(service.send_calls[0]["body"]["raw"]))
    assert mime["Subject"] == "Re: Already prefixed"
    assert "threadId" not in service.send_calls[0]["body"]
