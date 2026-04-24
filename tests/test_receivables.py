"""Receivables classifier + simple dunning text tests."""

import sys
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from core.receivables import (
    IncomeLite,
    classify_receivables,
    draft_dunning_text_simple,
)


def _inc(days_ago, **kw):
    today = kw.pop("today", date(2026, 4, 24))
    return IncomeLite(
        id=kw.pop("id", f"id-{days_ago}"),
        date=today - timedelta(days=days_ago),
        amount=Decimal(str(kw.pop("amount", 30000))),
        payer_name=kw.pop("payer_name", "Payer"),
        status=kw.pop("status", "invoiced"),
    )


class TestClassify:

    def test_received_excluded(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(60, today=today, status="received")],
            today=today,
        )
        assert statuses == []

    def test_cancelled_excluded(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(90, today=today, status="cancelled")],
            today=today,
        )
        assert statuses == []

    def test_pending_under_threshold(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(10, today=today)],
            today=today,
            overdue_threshold_days=30,
            hard_threshold_days=60,
        )
        assert len(statuses) == 1
        assert statuses[0].category == "pending"
        assert statuses[0].is_overdue is False

    def test_overdue_soft(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(45, today=today)],
            today=today,
            overdue_threshold_days=30,
            hard_threshold_days=60,
        )
        assert statuses[0].category == "overdue_soft"
        assert statuses[0].is_overdue is True

    def test_overdue_hard(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(90, today=today)],
            today=today,
            overdue_threshold_days=30,
            hard_threshold_days=60,
        )
        assert statuses[0].category == "overdue_hard"

    def test_sorted_most_overdue_first(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(10, id="a"), _inc(100, id="b"), _inc(45, id="c")],
            today=today,
        )
        assert [s.income.id for s in statuses] == ["b", "c", "a"]

    def test_boundary_exactly_threshold(self):
        today = date(2026, 4, 24)
        statuses = classify_receivables(
            [_inc(30, today=today)],
            today=today,
            overdue_threshold_days=30,
            hard_threshold_days=60,
        )
        assert statuses[0].category == "overdue_soft"


class TestDunningText:

    def test_polite_has_key_fields(self):
        txt = draft_dunning_text_simple(
            payer_name="ABC 公司",
            amount=Decimal(50000),
            invoice_date=date(2026, 3, 1),
            days_outstanding=45,
            tone="polite",
        )
        assert "ABC 公司" in txt
        assert "NT$ 50,000" in txt
        assert "2026-03-01" in txt
        assert "45" in txt

    def test_firm_has_action_request(self):
        txt = draft_dunning_text_simple(
            payer_name="X",
            amount=Decimal(10000),
            invoice_date=date(2026, 2, 15),
            days_outstanding=70,
            tone="firm",
        )
        assert "匯款" in txt or "付款" in txt

    def test_empty_payer_falls_back(self):
        txt = draft_dunning_text_simple(
            payer_name="",
            amount=Decimal(1000),
            invoice_date=date(2026, 4, 1),
            days_outstanding=5,
            tone="neutral",
        )
        assert "[業主]" in txt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
