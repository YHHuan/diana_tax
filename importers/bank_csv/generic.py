from decimal import Decimal
from pathlib import Path

from importers.common import IncomeDraft

from ._helpers import compact_join, load_csv_rows, parse_date, parse_decimal, pick_column


DATE_ALIASES = (
    "date",
    "日期",
    "交易日",
    "交易日期",
    "入帳日",
    "value date",
    "posting date",
)
AMOUNT_ALIASES = (
    "amount",
    "金額",
    "交易金額",
    "收入金額",
    "存入金額",
    "credit",
)
MEMO_ALIASES = (
    "memo",
    "備註",
    "摘要",
    "說明",
    "description",
    "details",
)


def parse(
    path: str | Path,
    *,
    column_map: dict[str, str] | None = None,
) -> list[IncomeDraft]:
    fieldnames, rows = load_csv_rows(path)
    if not fieldnames:
        return []

    column_map = column_map or {}
    date_column = pick_column(fieldnames, DATE_ALIASES, column_map.get("date"))
    amount_column = pick_column(fieldnames, AMOUNT_ALIASES, column_map.get("amount"))
    memo_column = pick_column(fieldnames, MEMO_ALIASES, column_map.get("memo"))

    missing = [
        name
        for name, value in (
            ("date", date_column),
            ("amount", amount_column),
            ("memo", memo_column),
        )
        if value is None
    ]
    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(f"generic bank CSV 缺少必要欄位: {missing_names}")

    drafts: list[IncomeDraft] = []
    for index, row in enumerate(rows, start=1):
        amount = parse_decimal(row.get(amount_column))
        if amount is None or amount <= Decimal("0"):
            continue

        drafts.append(
            IncomeDraft(
                date=parse_date(row.get(date_column)),
                amount=amount,
                currency="TWD",
                raw_description=compact_join(row.get(memo_column)),
                counterparty_hint=None,
                suggested_income_type=None,
                source="bank_csv:generic",
                source_row_id=str(index),
                confidence=0.6,
            )
        )

    return drafts
