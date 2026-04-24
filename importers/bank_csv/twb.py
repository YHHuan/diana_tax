from decimal import Decimal
from pathlib import Path

from importers.common import IncomeDraft

from ._helpers import compact_join, load_csv_rows, parse_date, parse_decimal, pick_column


DATE_ALIASES = (
    "交易日期",
    "交易日",
    "日期",
    "入帳日",
)
CREDIT_ALIASES = (
    "存入金額",
    "收入金額",
    "貸方金額",
    "收入",
)
DEBIT_ALIASES = (
    "支出金額",
    "提出金額",
    "借方金額",
    "支出",
)
AMOUNT_ALIASES = (
    "交易金額",
    "金額",
    "發生額",
)
SUMMARY_ALIASES = (
    "摘要",
    "備註",
    "說明",
    "交易內容",
)
COUNTERPARTY_ALIASES = (
    "對方戶名",
    "對方名稱",
    "匯款人",
    "付款人",
    "附言",
)
DIRECTION_ALIASES = (
    "借貸別",
    "收付別",
    "交易別",
)

INBOUND_KEYWORDS = ("存入", "轉入", "匯入", "收入", "貸方", "入帳", "收款")
OUTBOUND_KEYWORDS = ("支出", "轉出", "匯出", "借方", "付款", "扣款", "提款")
SELF_TRANSFER_KEYWORDS = ("自己轉帳", "本人轉帳", "本戶轉帳", "同戶名轉帳")


def parse(path: str | Path) -> list[IncomeDraft]:
    fieldnames, rows = load_csv_rows(path)
    if not fieldnames:
        return []

    date_column = pick_column(fieldnames, DATE_ALIASES)
    credit_column = pick_column(fieldnames, CREDIT_ALIASES)
    debit_column = pick_column(fieldnames, DEBIT_ALIASES)
    amount_column = pick_column(fieldnames, AMOUNT_ALIASES)
    summary_column = pick_column(fieldnames, SUMMARY_ALIASES)
    counterparty_column = pick_column(fieldnames, COUNTERPARTY_ALIASES)
    direction_column = pick_column(fieldnames, DIRECTION_ALIASES)

    if date_column is None:
        raise ValueError("Bank of Taiwan CSV 缺少日期欄位")

    drafts: list[IncomeDraft] = []
    for index, row in enumerate(rows, start=1):
        summary = row.get(summary_column, "") if summary_column else ""
        counterparty = row.get(counterparty_column, "") if counterparty_column else ""
        direction = row.get(direction_column, "") if direction_column else ""
        combined_text = " ".join((summary, counterparty, direction)).lower()

        if any(keyword in combined_text for keyword in SELF_TRANSFER_KEYWORDS):
            continue

        credit_amount = parse_decimal(row.get(credit_column)) if credit_column else None
        debit_amount = parse_decimal(row.get(debit_column)) if debit_column else None
        signed_amount = parse_decimal(row.get(amount_column)) if amount_column else None

        has_inbound_signal = any(keyword in combined_text for keyword in INBOUND_KEYWORDS)
        has_outbound_signal = any(keyword in combined_text for keyword in OUTBOUND_KEYWORDS)

        is_inflow = credit_amount is not None and credit_amount > 0
        if not is_inflow and signed_amount is not None and signed_amount > 0 and has_inbound_signal:
            is_inflow = True

        is_outflow = debit_amount is not None and debit_amount > 0
        if signed_amount is not None and signed_amount < 0:
            is_outflow = True
        if has_outbound_signal and not has_inbound_signal:
            is_outflow = True

        if is_outflow or not is_inflow:
            continue

        amount = credit_amount if credit_amount is not None and credit_amount > 0 else signed_amount
        if amount is None or amount <= Decimal("0"):
            continue

        drafts.append(
            IncomeDraft(
                date=parse_date(row.get(date_column)),
                amount=amount,
                currency="TWD",
                raw_description=compact_join(summary, counterparty),
                counterparty_hint=counterparty or None,
                suggested_income_type=None,
                source="bank_csv:twb",
                source_row_id=str(index),
                confidence=0.74 if credit_column else 0.7,
            )
        )

    return drafts
