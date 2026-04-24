from decimal import Decimal
from pathlib import Path

from importers.common import IncomeDraft

from ._helpers import (
    compact_join,
    load_csv_rows,
    normalize_header,
    parse_date,
    parse_decimal,
    pick_column,
)


DATE_ALIASES = (
    "交易日",
    "交易日期",
    "入帳日",
    "入帳日期",
    "日期",
    "Date",
)
CREDIT_ALIASES = (
    "存入金額",
    "收入金額",
    "貸方金額",
    "Deposit",
    "Credit",
    "Amount in",
)
DEBIT_ALIASES = (
    "支出金額",
    "提出金額",
    "借方金額",
    "Withdrawal",
    "Debit",
    "Amount out",
)
AMOUNT_ALIASES = (
    "交易金額",
    "金額",
    "Amount",
)
SUMMARY_ALIASES = (
    "摘要",
    "備註",
    "說明",
    "交易內容",
    "Description",
    "Memo",
    "Details",
)
COUNTERPARTY_ALIASES = (
    "對方戶名",
    "對方名稱",
    "匯款人",
    "付款人",
    "Counterparty",
    "Payee",
)
DIRECTION_ALIASES = (
    "收付別",
    "借貸別",
    "交易別",
    "Direction",
    "Type",
)

INBOUND_KEYWORDS = ("存入", "轉入", "匯入", "收入", "貸方", "入帳", "收款", "received", "deposit")
OUTBOUND_KEYWORDS = ("支出", "轉出", "匯出", "借方", "付款", "扣款", "提款", "sent", "payment", "card")
SELF_TRANSFER_KEYWORDS = ("自己轉帳", "本人轉帳", "本戶轉帳", "same account", "internal transfer")
RICHART_VARIANT_HEADERS = {
    "date",
    "description",
    "details",
    "amount",
    "credit",
    "debit",
}


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
        raise ValueError("E.SUN / Richart bank CSV 缺少日期欄位")

    normalized_headers = {normalize_header(name) for name in fieldnames}
    variant = "richart" if normalized_headers & RICHART_VARIANT_HEADERS else None

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
        if not is_inflow and signed_amount is not None and signed_amount > 0:
            is_inflow = not has_outbound_signal or has_inbound_signal

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

        extra = {"variant": variant} if variant else {}
        drafts.append(
            IncomeDraft(
                date=parse_date(row.get(date_column)),
                amount=amount,
                currency="TWD",
                raw_description=compact_join(summary, counterparty),
                counterparty_hint=counterparty or None,
                suggested_income_type=None,
                source="bank_csv:esun",
                source_row_id=str(index),
                confidence=0.74 if credit_column else 0.7,
                extra=extra,
            )
        )

    return drafts
