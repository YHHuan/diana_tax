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


def test_dispatcher_routes_richart_alias_to_esun_parser():
    drafts = parse(FIXTURES / "richart_sample.csv", "richart")

    assert len(drafts) == 1
    assert drafts[0].source == "bank_csv:esun"


def test_esun_inflow_rows_become_drafts_and_outflows_are_skipped():
    drafts = parse(FIXTURES / "esun_sample.csv", "esun")

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.date.isoformat() == "2025-04-18"
    assert draft.amount == Decimal("42000")
    assert draft.currency == "TWD"
    assert draft.raw_description == "跨行匯入講座費 | 某大學"
    assert draft.counterparty_hint == "某大學"
    assert draft.source == "bank_csv:esun"
    assert draft.source_row_id == "1"
    assert draft.extra == {}


def test_richart_shape_routes_through_esun_parser_and_marks_variant():
    drafts = parse(FIXTURES / "richart_sample.csv", "richart")

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.date.isoformat() == "2025-04-20"
    assert draft.amount == Decimal("3000")
    assert draft.raw_description == "Payment received invoice #381 | Acme Media Ltd"
    assert draft.source == "bank_csv:esun"
    assert draft.extra == {"variant": "richart"}


def test_twb_inflow_rows_become_drafts_and_roc_dates_are_supported():
    drafts = parse(FIXTURES / "twb_sample.csv", "twb")

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.date.isoformat() == "2025-04-22"
    assert draft.amount == Decimal("50000")
    assert draft.raw_description == "跨行匯入稿費 | 某出版社股份有限公司"
    assert draft.source == "bank_csv:twb"


def test_twb_outflow_only_csv_returns_no_drafts():
    assert parse(FIXTURES / "twb_outflow_only.csv", "twb") == []


def test_wise_parser_keeps_supported_currency_and_notes_fx_rows():
    drafts = parse(FIXTURES / "wise_sample.csv", "wise")

    assert len(drafts) == 2
    assert drafts[0].amount == Decimal("1250")
    assert drafts[0].currency == "USD"
    assert drafts[0].notes == "原始幣別 USD，尚未換算為 TWD。"
    assert drafts[0].source == "bank_csv:wise"

    assert drafts[1].amount == Decimal("30000")
    assert drafts[1].currency == "TWD"
    assert drafts[1].notes == ""


def test_wise_parser_skips_unsupported_currency_and_outflows():
    drafts = parse(FIXTURES / "wise_sample.csv", "wise")

    assert all(draft.amount > 0 for draft in drafts)
    assert {draft.currency for draft in drafts} == {"USD", "TWD"}


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
    assert parse(csv_path, "esun") == []
    assert parse(csv_path, "twb") == []
    assert parse(csv_path, "wise") == []
