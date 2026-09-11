"""
PHASE 6 — real Gmail ingestion + sending, via OAuth (integrations/google_auth.py).

fetch_new_emails() polls a specific label (GMAIL_LABEL_TO_POLL, default
"support") rather than the whole inbox, parses each message into the same
flat IncomingEmail shape fixtures use, and swaps the label off each message
it successfully parses.

Note on dedup: the DB's id-based dedup in api/main.py::_new_emails is the
correctness backstop regardless of what happens here (Gmail's message id
becomes IncomingEmail.id). The label swap below is pure hygiene/cost
control — without it, every poll would re-list and re-fetch full payloads
for an ever-growing pile of already-handled mail.

send_reply() is what api/db.py::approve_email() calls once a draft is
approved for a Gmail-sourced email — proper threading needs both Gmail's
`threadId` and the RFC822 `Message-ID` header of the original message (not
the Gmail id) for In-Reply-To/References, so it's fetched on demand.
"""
from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Optional

from googleapiclient.discovery import build

from agent.schemas import IncomingEmail
from integrations import google_auth

DEFAULT_LABEL = "support"
_MAX_RESULTS = 25  # one page per poll — no auto-pagination (see plan's known limitations)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _decode_body_data(data: str) -> str:
    """Gmail body data is base64url, sometimes missing padding."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    """Deliberately naive — good enough for feeding a classifier/drafter,
    not a real HTML-to-text pipeline."""
    text = _HTML_TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


def _find_part(payload: dict, mime_type: str) -> Optional[str]:
    """Recursively searches a (possibly multipart) message payload for the
    first part matching mime_type, returning its raw base64url body data."""
    if payload.get("mimeType") == mime_type:
        data = payload.get("body", {}).get("data")
        if data:
            return data
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime_type)
        if found is not None:
            return found
    return None


def _extract_body(payload: dict) -> str:
    """Prefers text/plain; falls back to a stripped text/html part."""
    plain = _find_part(payload, "text/plain")
    if plain is not None:
        return _decode_body_data(plain).strip()
    html = _find_part(payload, "text/html")
    if html is not None:
        return _strip_html(_decode_body_data(html))
    return ""


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_message(raw: dict) -> IncomingEmail:
    """Pure — no auth/network. Maps a Gmail API message resource (format='full')
    into the same flat shape ingest/fixture_loader.py produces."""
    payload = raw.get("payload", {})
    headers = payload.get("headers", [])
    _, from_address = parseaddr(_header(headers, "From"))
    subject = _header(headers, "Subject")
    body = _extract_body(payload)

    received_at = None
    internal_date = raw.get("internalDate")
    if internal_date:
        received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)

    return IncomingEmail(
        id=raw["id"],
        from_address=from_address or "unknown@unknown",
        subject=subject,
        body=body,
        thread_id=raw.get("threadId"),
        received_at=received_at,
        source="gmail",
    )


def _resolve_label_id(service, label_name: str) -> str:
    resp = service.users().labels().list(userId="me").execute()
    for label in resp.get("labels", []):
        if label["name"].lower() == label_name.lower():
            return label["id"]
    raise ValueError(
        f"No Gmail label named '{label_name}' — create it in Gmail first "
        "(see GMAIL_LABEL_TO_POLL in .env)."
    )


def _mark_processed(service, label_id: str, message_ids: list[str]) -> None:
    for message_id in message_ids:
        service.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": [label_id]},
        ).execute()


def fetch_new_emails(label: Optional[str] = None) -> list[IncomingEmail]:
    """One page (up to _MAX_RESULTS) of unprocessed messages under `label`."""
    label = label or os.environ.get("GMAIL_LABEL_TO_POLL", DEFAULT_LABEL)
    creds = google_auth.get_credentials()
    service = build("gmail", "v1", credentials=creds)

    label_id = _resolve_label_id(service, label)
    resp = service.users().messages().list(
        userId="me", labelIds=[label_id], maxResults=_MAX_RESULTS,
    ).execute()
    stubs = resp.get("messages", []) or []

    emails: list[IncomingEmail] = []
    parsed_ids: list[str] = []
    for stub in stubs:
        raw = service.users().messages().get(userId="me", id=stub["id"], format="full").execute()
        emails.append(_parse_message(raw))
        parsed_ids.append(stub["id"])

    if parsed_ids:
        _mark_processed(service, label_id, parsed_ids)

    return emails


def send_reply(*, original_message_id: str, thread_id: Optional[str],
                to_address: str, subject: str, body_text: str) -> dict:
    """Sends body_text as a reply in the same Gmail thread as original_message_id."""
    creds = google_auth.get_credentials()
    service = build("gmail", "v1", credentials=creds)

    meta = service.users().messages().get(
        userId="me", id=original_message_id, format="metadata",
        metadataHeaders=["Message-ID"],
    ).execute()
    original_rfc_id = _header(meta.get("payload", {}).get("headers", []), "Message-ID")

    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message = MIMEText(body_text)
    message["To"] = to_address
    message["Subject"] = subject
    if original_rfc_id:
        message["In-Reply-To"] = original_rfc_id
        message["References"] = original_rfc_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    send_body: dict = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    return service.users().messages().send(userId="me", body=send_body).execute()
