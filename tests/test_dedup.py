import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Income
from importers.common import IncomeDraft
from importers.dedup import find_batch_duplicates, find_existing_duplicates, texts_look_duplicate


def _draft(**overrides):
    payload = {
        "date": date(2025, 4, 18),
        "amount": Decimal("42000"),
        "currency": "TWD",
        "raw_description": "某出版社 匯入稿費",
        "counterparty_hint": "某出版社",
        "source": "bank_csv:esun",
    }
    payload.update(overrides)
    return IncomeDraft(**payload)


def _income(**overrides):
    payload = {
        "date": date(2025, 4, 18),
        "amount": Decimal("42000"),
        "currency": "TWD",
        "income_type": "9B_author",
        "tax_year": 114,
        "tax_withheld": Decimal("0"),
        "nhi_withheld": Decimal("0"),
        "status": "received",
        "received_date": date(2025, 4, 18),
        "notes": "某出版社 | 匯入稿費",
        "source": "gmail_import",
        "created_at": datetime.now(UTC).replace(tzinfo=None),
        "updated_at": datetime.now(UTC).replace(tzinfo=None),
    }
    payload.update(overrides)
    return Income(**payload)


def test_texts_look_duplicate_matches_sender_and_counterparty():
    assert texts_look_duplicate("某出版社 匯款通知", "某出版社 | 匯入稿費")


def test_find_batch_duplicates_flags_second_copy():
    duplicates = find_batch_duplicates([_draft(), _draft(source_row_id="2")])

    assert duplicates == {1: "與同批第 1 筆重複"}


def test_find_existing_duplicates_flags_cross_source_match():
    duplicates = find_existing_duplicates([_draft()], [_income()])

    assert "與既有收入重複" in duplicates[0]
