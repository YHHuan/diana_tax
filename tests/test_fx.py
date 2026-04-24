import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.fx import convert_amount_to_twd, convert_draft_to_twd, convert_drafts_to_twd
from importers.common import IncomeDraft


def _draft(**overrides):
    payload = {
        "date": date(2025, 4, 23),
        "amount": Decimal("1250"),
        "currency": "USD",
        "raw_description": "Wise payout",
        "counterparty_hint": "Client A",
        "source": "bank_csv:wise",
        "source_row_id": "1",
        "notes": "",
    }
    payload.update(overrides)
    return IncomeDraft(**payload)


def test_convert_amount_to_twd_rounds_half_up():
    assert convert_amount_to_twd(Decimal("1000"), Decimal("31.234")) == Decimal("31234")


def test_convert_draft_to_twd_preserves_original_values_in_extra():
    converted = convert_draft_to_twd(_draft(), {"USD": Decimal("31.8")})

    assert converted.amount == Decimal("39750")
    assert converted.currency == "TWD"
    assert converted.extra["original_amount"] == "1250"
    assert converted.extra["original_currency"] == "USD"
    assert converted.extra["fx_rate_to_twd"] == "31.8"
    assert "採匯率 31.8 換算為 TWD 39750" in converted.notes


def test_convert_drafts_to_twd_collects_missing_rate_warning():
    converted, warnings = convert_drafts_to_twd([_draft(currency="JPY", amount=Decimal("10000"))], {})

    assert converted == []
    assert warnings == ["1: 缺少 JPY -> TWD 匯率"]
