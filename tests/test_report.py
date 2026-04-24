"""Markdown report builder tests."""

import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from core.report import build_markdown_report, IncomeRow, SlipRow
from core.report_pdf import render_markdown_pdf


def _inc(**kw):
    return IncomeRow(
        date=kw.get("date", date(2026, 4, 1)),
        payer_name=kw.get("payer_name", "ABC"),
        amount=Decimal(str(kw.get("amount", 10000))),
        income_type=kw.get("income_type", "9B_speech"),
        tax_withheld=Decimal(str(kw.get("tax_withheld", 0))),
        nhi_withheld=Decimal(str(kw.get("nhi_withheld", 0))),
    )


def test_empty_report_has_no_crash_and_zero_tax():
    md = build_markdown_report(tax_year=114, incomes=[], slips=[])
    assert "114 年度" in md
    assert "**應納稅額** | **NT$ 0**" in md


def test_report_includes_user_name_and_filing_window():
    md = build_markdown_report(
        tax_year=114, incomes=[], slips=[], user_name="黃雅涵",
    )
    assert "黃雅涵" in md
    assert "2026-05-01" in md


def test_small_author_income_fully_exempt():
    md = build_markdown_report(
        tax_year=114,
        incomes=[_inc(amount=150_000, income_type="9B_author", tax_withheld=15_000)],
        slips=[],
    )
    assert "全額免稅" in md
    # refund = 15000 (since taxable is 0, withheld 15000 → refund)
    assert "**= 可退稅** | **NT$ 15,000**" in md


def test_mismatch_flag_when_income_differs_from_slip():
    md = build_markdown_report(
        tax_year=114,
        incomes=[_inc(amount=100_000, payer_name="ABC")],
        slips=[SlipRow(
            payer_name="ABC",
            payer_tax_id="12345678",
            income_type="9B_speech",
            gross_amount=Decimal(50_000),
            tax_withheld=Decimal(5_000),
            nhi_withheld=Decimal(0),
        )],
    )
    assert "Income 多" in md or "Income 少" in md


def test_multiple_income_types_all_listed():
    md = build_markdown_report(
        tax_year=114,
        incomes=[
            _inc(income_type="50", amount=500_000),
            _inc(income_type="9A", amount=100_000),
            _inc(income_type="9B_author", amount=200_000),
        ],
        slips=[],
    )
    assert "薪資所得（50）" in md
    assert "執行業務所得（9A）" in md
    assert "稿費 / 版稅（9B）" in md


def test_itemized_deduction_overrides_standard():
    md_std = build_markdown_report(tax_year=114, incomes=[], slips=[])
    md_itm = build_markdown_report(
        tax_year=114, incomes=[], slips=[], itemized_deduction=Decimal(200_000),
    )
    assert "標準扣除額" in md_std
    assert "列舉扣除額" in md_itm


def test_markdown_can_render_to_pdf_bytes():
    md = build_markdown_report(
        tax_year=114,
        incomes=[_inc(amount=50_000, income_type="9B_speech", payer_name="某大學")],
        slips=[],
        user_name="黃雅涵",
    )

    pdf_bytes = render_markdown_pdf(md, title="test")

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
