from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from core.models import Income
from .common import IncomeDraft


TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}")


@dataclass
class DuplicateHint:
    index: int
    reason: str


def normalize_text(value: str | None) -> str:
    lowered = str(value or "").lower().strip()
    return re.sub(r"[\W_]+", "", lowered)


def tokenize_text(value: str | None) -> set[str]:
    return set(TOKEN_RE.findall(str(value or "").lower()))


def draft_text(draft: IncomeDraft) -> str:
    return " ".join(
        part for part in (draft.counterparty_hint, draft.raw_description) if str(part or "").strip()
    )


def income_text(income: Income) -> str:
    return str(income.notes or "").strip()


def same_amount(a: Decimal, b: Decimal) -> bool:
    return a == b


def texts_look_duplicate(a: str | None, b: str | None) -> bool:
    """Strong-signal text overlap. Addresses auto-review finding:
    "any shared 2-char token" was too aggressive — generic CJK words
    like 顧問費/公司/服務 caused false positives on two distinct same-day
    invoices from different clients.

    Match rule now:
      1. Both texts empty → ambiguous, let other signatures decide (True).
      2. Normalized equality or substring containment → True.
      3. Shared token with proper-noun-ish length (CJK ≥4 / latin ≥5) → True.
      4. Otherwise False.
    """
    norm_a = normalize_text(a)
    norm_b = normalize_text(b)
    if not norm_a and not norm_b:
        return True
    if norm_a and norm_b and (norm_a == norm_b or norm_a in norm_b or norm_b in norm_a):
        return True

    def _is_strong_token(t: str) -> bool:
        if not t:
            return False
        return len(t) >= 5 if t.isascii() else len(t) >= 4

    shared = tokenize_text(a) & tokenize_text(b)
    return any(_is_strong_token(tok) for tok in shared)


def same_income_signature(draft: IncomeDraft, income: Income) -> bool:
    if draft.date != income.date:
        return False
    if str(draft.currency or "TWD").upper() != str(income.currency or "TWD").upper():
        return False
    if not same_amount(draft.amount, income.amount):
        return False
    return texts_look_duplicate(draft_text(draft), income_text(income))


def find_batch_duplicates(drafts: list[IncomeDraft]) -> dict[int, str]:
    seen: dict[tuple[object, ...], int] = {}
    duplicates: dict[int, str] = {}

    for index, draft in enumerate(drafts):
        key = (
            draft.date,
            draft.amount,
            str(draft.currency or "TWD").upper(),
            normalize_text(draft_text(draft)),
        )
        previous = seen.get(key)
        if previous is not None:
            duplicates[index] = f"與同批第 {previous + 1} 筆重複"
            continue
        seen[key] = index
    return duplicates


def find_existing_duplicates(drafts: list[IncomeDraft], incomes: list[Income]) -> dict[int, str]:
    duplicates: dict[int, str] = {}

    for index, draft in enumerate(drafts):
        for income in incomes:
            if same_income_signature(draft, income):
                duplicates[index] = (
                    f"與既有收入重複：{income.date.isoformat()} / "
                    f"{income.amount} {income.currency}"
                )
                break
    return duplicates
