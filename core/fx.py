from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP

from importers.common import IncomeDraft


SUPPORTED_FX_CURRENCIES = {"USD", "JPY"}
TWD_QUANTIZE = Decimal("1")


def parse_fx_rate(value: object) -> Decimal | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    rate = Decimal(raw)
    if rate <= 0:
        raise ValueError("匯率必須大於 0")
    return rate


def convert_amount_to_twd(amount: Decimal, rate_to_twd: Decimal) -> Decimal:
    return (amount * rate_to_twd).quantize(TWD_QUANTIZE, rounding=ROUND_HALF_UP)


def convert_draft_to_twd(draft: IncomeDraft, fx_rates: dict[str, Decimal]) -> IncomeDraft:
    currency = str(draft.currency or "TWD").upper()
    if currency == "TWD":
        return draft

    rate = fx_rates.get(currency)
    if rate is None:
        raise ValueError(f"缺少 {currency} -> TWD 匯率")

    converted_amount = convert_amount_to_twd(draft.amount, rate)
    extra = dict(draft.extra)
    extra.update(
        {
            "original_amount": str(draft.amount),
            "original_currency": currency,
            "fx_rate_to_twd": str(rate),
            "converted_amount_twd": str(converted_amount),
        }
    )

    fx_note = f"原始幣別 {currency} {draft.amount}，採匯率 {rate} 換算為 TWD {converted_amount}。"
    notes = draft.notes.strip()
    notes = f"{notes}\n{fx_note}".strip() if notes else fx_note

    return replace(
        draft,
        amount=converted_amount,
        currency="TWD",
        notes=notes,
        extra=extra,
    )


def convert_drafts_to_twd(
    drafts: list[IncomeDraft],
    fx_rates: dict[str, Decimal],
) -> tuple[list[IncomeDraft], list[str]]:
    converted: list[IncomeDraft] = []
    warnings: list[str] = []

    for draft in drafts:
        currency = str(draft.currency or "TWD").upper()
        if currency == "TWD":
            converted.append(draft)
            continue

        if currency not in SUPPORTED_FX_CURRENCIES:
            warnings.append(f"{draft.source_row_id or '?'}: 不支援的幣別 {currency}")
            continue

        try:
            converted.append(convert_draft_to_twd(draft, fx_rates))
        except ValueError as exc:
            warnings.append(f"{draft.source_row_id or '?'}: {exc}")

    return converted, warnings
