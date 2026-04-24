import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from importers.bank_csv import parse


FIXTURES = ROOT / "tests" / "fixtures" / "bank_csv"


def test_cathay_inflow_rows_become_drafts_and_outflows_are_skipped():
    drafts = parse(FIXTURES / "cathay_sample.csv", "cathay")

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.date.isoformat() == "2025-04-15"
    assert draft.amount == Decimal("50000")
    assert draft.currency == "TWD"
    assert draft.raw_description == "跨行匯入稿費 | 某出版社股份有限公司"
    assert draft.counterparty_hint == "某出版社股份有限公司"
    assert draft.suggested_income_type is None
    assert draft.source == "bank_csv:cathay"
    assert draft.source_row_id == "1"
    assert Decimal("0.6") <= Decimal(str(draft.confidence)) <= Decimal("0.8")


def test_generic_parser_detects_columns_and_parses_decimal():
    drafts = parse(FIXTURES / "generic_sample.csv", "generic")

    assert len(drafts) == 1
    draft = drafts[0]
    assert isinstance(draft.amount, Decimal)
    assert draft.amount == Decimal("30000")
    assert draft.raw_description == "演講鐘點費"
    assert draft.source == "bank_csv:generic"


def test_dispatcher_routes_supported_non_cathay_banks_to_generic():
    drafts = parse(FIXTURES / "generic_sample.csv", "wise")

    assert len(drafts) == 1
    assert drafts[0].source == "bank_csv:generic"


def test_generic_column_map_override(tmp_path):
    csv_path = tmp_path / "mapped.csv"
    csv_path.write_text(
        "交易日期,入帳,說明欄\n2025/04/21,42000,專欄稿費\n",
        encoding="utf-8",
    )

    drafts = parse(
        csv_path,
        "generic",
        column_map={"date": "交易日期", "amount": "入帳", "memo": "說明欄"},
    )

    assert len(drafts) == 1
    assert drafts[0].amount == Decimal("42000")
    assert drafts[0].raw_description == "專欄稿費"


def test_empty_csv_returns_empty_list(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    assert parse(csv_path, "generic") == []
    assert parse(csv_path, "cathay") == []
