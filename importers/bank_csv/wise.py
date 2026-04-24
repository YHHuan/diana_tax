from decimal import Decimal
from pathlib import Path

from importers.common import IncomeDraft

from ._helpers import compact_join, load_csv_rows, parse_date, parse_decimal, pick_column


SUPPORTED_CURRENCIES = {"TWD", "USD", "JPY"}

DATE_ALIASES = (
    "Date",
    "date",
    "Created on",
    "交易日期",
)
AMOUNT_ALIASES = (
    "Amount",
    "金額",
    "Net amount",
)
CREDIT_ALIASES = (
    "Credit",
    "Amount in",
)
DEBIT_ALIASES = (
    "Debit",
    "Amount out",
)
CURRENCY_ALIASES = (
    "Currency",
    "currency",
    "幣別",
)
SUMMARY_ALIASES = (
    "Description",
    "description",
    "Details",
    "details",
    "備註",
    "摘要",
)
COUNTERPARTY_ALIASES = (
    "Counterparty",
    "counterparty",
    "Recipient",
    "Payer",
)
TYPE_ALIASES = (
    "Type",
    "type",
    "Direction",
)

INBOUND_KEYWORDS = (
    "received",
    "deposit",
    "invoice",
    "payment received",
    "money added",
    "transfer in",
)
OUTBOUND_KEYWORDS = (
    "sent",
    "card",
    "withdrawal",
    "fee",
    "charge",
    "transfer out",
    "payment",
)


def parse(path: str | Path) -> list[IncomeDraft]:
    fieldnames, rows = load_csv_rows(path)
    if not fieldnames:
        return []

    date_column = pick_column(fieldnames, DATE_ALIASES)
    amount_column = pick_column(fieldnames, AMOUNT_ALIASES)
    credit_column = pick_column(fieldnames, CREDIT_ALIASES)
    debit_column = pick_column(fieldnames, DEBIT_ALIASES)
    currency_column = pick_column(fieldnames, CURRENCY_ALIASES)
    summary_column = pick_column(fieldnames, SUMMARY_ALIASES)
    counterparty_column = pick_column(fieldnames, COUNTERPARTY_ALIASES)
    type_column = pick_column(fieldnames, TYPE_ALIASES)

    missing = [
        name
        for name, value in (
            ("date", date_column),
            ("amount", amount_column if amount_column or credit_column else None),
            ("currency", currency_column),
        )
        if value is None
    ]
    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(f"Wise bank CSV 缺少必要欄位: {missing_names}")

    drafts: list[IncomeDraft] = []
    for index, row in enumerate(rows, start=1):
        summary = row.get(summary_column, "") if summary_column else ""
        counterparty = row.get(counterparty_column, "") if counterparty_column else ""
        direction = row.get(type_column, "") if type_column else ""
        combined_text = " ".join((summary, counterparty, direction)).lower()

        credit_amount = parse_decimal(row.get(credit_column)) if credit_column else None
        debit_amount = parse_decimal(row.get(debit_column)) if debit_column else None
        signed_amount = parse_decimal(row.get(amount_column)) if amount_column else None

        is_inflow = credit_amount is not None and credit_amount > 0
        if not is_inflow and signed_amount is not None and signed_amount > 0:
            is_inflow = not any(keyword in combined_text for keyword in OUTBOUND_KEYWORDS)
        if not is_inflow and any(keyword in combined_text for keyword in INBOUND_KEYWORDS):
            is_inflow = signed_amount is None or signed_amount >= 0

        is_outflow = debit_amount is not None and debit_amount > 0
        if signed_amount is not None and signed_amount < 0:
            is_outflow = True
        if any(keyword in combined_text for keyword in OUTBOUND_KEYWORDS) and not any(
            keyword in combined_text for keyword in INBOUND_KEYWORDS
        ):
            is_outflow = True

        if is_outflow or not is_inflow:
            continue

        amount = credit_amount if credit_amount is not None and credit_amount > 0 else signed_amount
        if amount is None or amount <= Decimal("0"):
            continue

        currency = str(row.get(currency_column, "") or "").strip().upper()
        if currency not in SUPPORTED_CURRENCIES:
            continue

        notes = ""
        if currency != "TWD":
            notes = f"原始幣別 {currency}，尚未換算為 TWD。"

        drafts.append(
            IncomeDraft(
                date=parse_date(row.get(date_column)),
                amount=amount,
                currency=currency,
                raw_description=compact_join(summary, counterparty),
                counterparty_hint=counterparty or None,
                suggested_income_type=None,
                source="bank_csv:wise",
                source_row_id=str(index),
                confidence=0.78 if credit_column else 0.74,
                notes=notes,
            )
        )

    return drafts
