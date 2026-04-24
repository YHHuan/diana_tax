from __future__ import annotations

import base64
import email.utils
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .common import IncomeDraft


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_GMAIL_QUERY = (
    "newer_than:90d (匯款 OR 入帳 OR 已付款 OR remittance OR payment OR wire)"
)

AMOUNT_PATTERNS = (
    re.compile(
        r"(?:金額|付款金額|匯款金額|payment amount|amount)[^0-9A-Z]{0,12}"
        r"(NT\$|TWD|USD|JPY)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        re.IGNORECASE,
    ),
    re.compile(r"(NT\$|TWD|USD|JPY)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.IGNORECASE),
)
INCOME_KEYWORDS = (
    "匯款",
    "入帳",
    "已付款",
    "撥款",
    "remittance",
    "payment",
    "wire",
    "deposit",
    "paid",
)


class GmailNotConfigured(RuntimeError):
    pass


def _import_google_modules():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailNotConfigured(
            "缺少 Gmail 依賴。請安裝 google-api-python-client 與 google-auth-oauthlib。"
        ) from exc

    return Request, Credentials, InstalledAppFlow, build


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode(data + padding)
    return decoded.decode("utf-8", errors="ignore")


def _collect_payload_text(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")

    if mime_type.startswith("text/"):
        return _decode_body(body_data)

    texts: list[str] = []
    for part in payload.get("parts", []) or []:
        text = _collect_payload_text(part)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _header_value(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value", "")).strip()
    return ""


def _parsed_datetime(value: str) -> datetime:
    dt = email.utils.parsedate_to_datetime(value)
    if dt is None:
        raise ValueError(f"無法解析 email 日期: {value}")
    return dt


def _sender_name(value: str) -> str:
    name, address = email.utils.parseaddr(value)
    return name or address


def extract_amount(text: str) -> tuple[Decimal, str] | None:
    for pattern in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        currency = (match.group(1) or "TWD").upper()
        if currency == "NT$":
            currency = "TWD"
        amount = Decimal(match.group(2).replace(",", ""))
        return amount, currency
    return None


def build_income_draft_from_message(message: dict[str, Any]) -> IncomeDraft | None:
    payload = message.get("payload", {})
    headers = payload.get("headers", []) or []
    subject = _header_value(headers, "Subject")
    sender = _header_value(headers, "From")
    date_header = _header_value(headers, "Date")
    snippet = str(message.get("snippet", "") or "").strip()
    body_text = _collect_payload_text(payload)

    combined = "\n".join(part for part in (subject, snippet, body_text) if part).strip()
    if not combined:
        return None

    lowered = combined.lower()
    if not any(keyword in lowered for keyword in INCOME_KEYWORDS):
        return None

    extracted = extract_amount(combined)
    if extracted is None:
        return None

    amount, currency = extracted
    sender_name = _sender_name(sender)
    sent_at = _parsed_datetime(date_header) if date_header else datetime.utcnow()

    return IncomeDraft(
        date=sent_at.date(),
        amount=amount,
        currency=currency,
        raw_description=subject or snippet or "Gmail 匯款通知",
        counterparty_hint=sender_name or None,
        source="gmail_import",
        source_row_id=str(message.get("id") or ""),
        confidence=0.7 if subject and sender_name else 0.62,
        notes=f"Gmail query 命中；寄件者 {sender_name or 'unknown'}；message_id={message.get('id', '')}",
        extra={
            "gmail_message_id": str(message.get("id") or ""),
            "gmail_thread_id": str(message.get("threadId") or ""),
            "gmail_sender": sender,
            "gmail_subject": subject,
        },
    )


def build_gmail_service(
    credentials_path: str | Path,
    token_path: str | Path,
):
    Request, Credentials, InstalledAppFlow, build = _import_google_modules()

    credentials_path = Path(credentials_path)
    token_path = Path(token_path)
    if not credentials_path.exists():
        raise GmailNotConfigured(f"Gmail OAuth client secret 不存在：{credentials_path}")

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def fetch_income_drafts_from_gmail(
    credentials_path: str | Path,
    token_path: str | Path,
    *,
    query: str = DEFAULT_GMAIL_QUERY,
    max_results: int = 20,
) -> list[IncomeDraft]:
    service = build_gmail_service(credentials_path, token_path)
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    drafts: list[IncomeDraft] = []
    for item in response.get("messages", []) or []:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        draft = build_income_draft_from_message(message)
        if draft is not None:
            drafts.append(draft)
    return drafts


def save_uploaded_gmail_credentials(
    raw_json: bytes,
    destination: str | Path,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    parsed = json.loads(raw_json.decode("utf-8"))
    destination.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
