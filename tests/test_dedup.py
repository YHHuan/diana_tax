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


def test_texts_look_duplicate_rejects_only_generic_shared_words():
    """兩個不同業主，同日同金額，描述都是常見詞 → 不該被誤標重複。
    修 auto-review 發現的 bug：原本任何 2-char 共同 token 就觸發，
    顧問費/公司 這種通用詞造成 false positive。"""
    assert not texts_look_duplicate("A 公司 顧問費", "B 公司 顧問費")
    assert not texts_look_duplicate("ABC 服務費", "XYZ 服務費")


def test_texts_look_duplicate_keeps_long_proper_noun_signal():
    """案主名通常 ≥ 4 CJK 字 → 仍應標為重複。"""
    assert texts_look_duplicate(
        "跨行匯入 某出版社股份有限公司",
        "某出版社股份有限公司 入帳",
    )


def test_find_existing_duplicates_skips_different_clients_same_day():
    """同日同金額但描述不同業主 → 不該自動擋。"""
    draft_a = _draft(raw_description="A 公司 顧問費", counterparty_hint="A 公司")
    inc_b = _income(notes="B 公司 | 顧問費")
    assert find_existing_duplicates([draft_a], [inc_b]) == {}


def test_find_batch_duplicates_flags_second_copy():
    duplicates = find_batch_duplicates([_draft(), _draft(source_row_id="2")])

    assert duplicates == {1: "與同批第 1 筆重複"}


def test_find_existing_duplicates_flags_cross_source_match():
    duplicates = find_existing_duplicates([_draft()], [_income()])

    assert "與既有收入重複" in duplicates[0]
