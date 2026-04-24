import base64
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from importers.email_gmail import build_income_draft_from_message, save_uploaded_gmail_credentials


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def test_build_income_draft_from_message_parses_subject_sender_and_amount():
    message = {
        "id": "abc123",
        "threadId": "thread456",
        "snippet": "某出版社已付款 NT$ 42,000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "稿費已付款 NT$ 42,000"},
                {"name": "From", "value": "某出版社 <finance@example.com>"},
                {"name": "Date", "value": "Fri, 18 Apr 2025 10:20:00 +0800"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64("付款金額：NT$ 42,000")},
        },
    }

    draft = build_income_draft_from_message(message)

    assert draft is not None
    assert draft.amount == Decimal("42000")
    assert draft.currency == "TWD"
    assert draft.date.isoformat() == "2025-04-18"
    assert draft.counterparty_hint == "某出版社"
    assert draft.source == "gmail_import"
    assert draft.extra["gmail_message_id"] == "abc123"


def test_non_income_message_is_skipped():
    message = {
        "id": "abc123",
        "snippet": "本月電子報",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Newsletter"},
                {"name": "From", "value": "news@example.com"},
                {"name": "Date", "value": "Fri, 18 Apr 2025 10:20:00 +0800"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64("Hello world")},
        },
    }

    assert build_income_draft_from_message(message) is None


def test_save_uploaded_gmail_credentials_writes_json(tmp_path):
    payload = {"installed": {"client_id": "abc"}}
    target = tmp_path / "client_secret.json"

    saved = save_uploaded_gmail_credentials(json.dumps(payload).encode("utf-8"), target)

    assert saved == target
    assert json.loads(target.read_text(encoding="utf-8")) == payload
