"""
報稅草稿產出 — Markdown 格式，Diana 5 月對著財政部官方軟體填。

設計原則：
- pure function，讀 Income / WithholdingSlip / UserSettings → 回 str
- 結構化分段：每種所得類別分別列表 + 合計，對照 MyData 容易
- 包含試算結果：綜合所得淨額、應納稅、扣繳對比、預估退補

未來可以加 weasyprint 或 reportlab 轉 PDF。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from .tax_engine import AnnualTaxResult, calculate_annual_tax
from . import rules_114 as R


def _fmt(n) -> str:
    """NT$ 金額格式化，千分位。"""
    if n is None:
        return "—"
    try:
        return f"NT$ {int(Decimal(str(n))):,}"
    except Exception:
        return str(n)


@dataclass
class SlipRow:
    """最小扣繳憑單 row，避免綁死 SQLModel — 讓 report 可以吃 dict 也可以吃 model"""
    payer_name: str
    payer_tax_id: Optional[str]
    income_type: str
    gross_amount: Decimal
    tax_withheld: Decimal
    nhi_withheld: Decimal


@dataclass
class IncomeRow:
    """最小收入 row"""
    date: date
    payer_name: str
    amount: Decimal
    income_type: str
    tax_withheld: Decimal
    nhi_withheld: Decimal


def build_markdown_report(
    tax_year: int,
    incomes: list[IncomeRow],
    slips: list[SlipRow],
    *,
    is_married: bool = False,
    dependents: int = 0,
    has_elderly_dependent: bool = False,
    occupation: str = "default",
    itemized_deduction: Optional[Decimal] = None,
    user_name: str = "",
) -> str:
    """產出 Markdown 報稅草稿。"""
    tr: AnnualTaxResult = calculate_annual_tax(
        incomes=[{"amount": i.amount, "income_type": i.income_type} for i in incomes],
        is_married=is_married,
        dependents=dependents,
        has_elderly_dependent=has_elderly_dependent,
        occupation=occupation,
        itemized_deduction=itemized_deduction,
    )
    # Pull withholding from Income rows
    tr.total_tax_withheld = sum((i.tax_withheld for i in incomes), Decimal(0))
    tr.total_nhi_withheld = sum((i.nhi_withheld for i in incomes), Decimal(0))
    tr.tax_owed_or_refund = tr.tax_payable - tr.total_tax_withheld

    lines: list[str] = []
    lines.append(f"# {tax_year} 年度綜合所得稅 申報草稿")
    lines.append("")
    if user_name:
        lines.append(f"**納稅義務人**：{user_name}")
    filing_window = R.FILING_WINDOW if tax_year == R.TAX_YEAR else ("?", "?")
    lines.append(
        f"**申報年度**：{tax_year}　　**申報期間**：{filing_window[0]} – {filing_window[1]}"
    )
    lines.append("")
    lines.append(
        "> ⚠️ 這是 Diana Tax 試算器產出的草稿，**不代表申報結果**。"
        "請以財政部電子申報系統為準。"
    )
    lines.append("")

    # ---- 收入明細（分類列出）----
    lines.append("## 一、收入明細")
    lines.append("")
    by_type: dict[str, list[IncomeRow]] = {}
    for inc in incomes:
        by_type.setdefault(inc.income_type, []).append(inc)

    for code in ["50", "9A", "9B_author", "9B_speech", "9B_other", "92", "overseas"]:
        rows = by_type.get(code, [])
        if not rows:
            continue
        label = R.INCOME_TYPE_LABELS_ZH.get(code, code)
        subtotal = sum((r.amount for r in rows), Decimal(0))
        withheld = sum((r.tax_withheld for r in rows), Decimal(0))
        nhi = sum((r.nhi_withheld for r in rows), Decimal(0))
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| 日期 | 業主 | 金額 | 已扣稅 | 已扣健保 |")
        lines.append("|---|---|---:|---:|---:|")
        for r in sorted(rows, key=lambda x: x.date):
            lines.append(
                f"| {r.date.isoformat()} | {r.payer_name or '—'} | "
                f"{_fmt(r.amount)} | {_fmt(r.tax_withheld)} | {_fmt(r.nhi_withheld)} |"
            )
        lines.append(
            f"| **小計** | **{len(rows)} 筆** | **{_fmt(subtotal)}** | "
            f"**{_fmt(withheld)}** | **{_fmt(nhi)}** |"
        )
        lines.append("")

    if not incomes:
        lines.append("_本年度尚無收入紀錄。_")
        lines.append("")

    # ---- 扣繳憑單對照 ----
    lines.append("## 二、業主扣繳憑單（對照 MyData）")
    lines.append("")
    if slips:
        lines.append("| 業主 | 統編 | 類別 | 給付總額 | 扣繳稅 | 扣繳健保 |")
        lines.append("|---|---|---|---:|---:|---:|")
        for s in slips:
            label = R.INCOME_TYPE_LABELS_ZH.get(s.income_type, s.income_type)
            lines.append(
                f"| {s.payer_name} | {s.payer_tax_id or '—'} | {label} | "
                f"{_fmt(s.gross_amount)} | {_fmt(s.tax_withheld)} | {_fmt(s.nhi_withheld)} |"
            )
        slip_gross = sum((s.gross_amount for s in slips), Decimal(0))
        slip_tax = sum((s.tax_withheld for s in slips), Decimal(0))
        slip_nhi = sum((s.nhi_withheld for s in slips), Decimal(0))
        lines.append(
            f"| **合計** | | | **{_fmt(slip_gross)}** | **{_fmt(slip_tax)}** | **{_fmt(slip_nhi)}** |"
        )
    else:
        lines.append("_尚未登錄任何扣繳憑單。5 月到 MyData 下載後上傳可自動比對。_")
    lines.append("")

    # ---- 差異檢核 ----
    if slips and incomes:
        lines.append("### 差異檢核（Income vs 扣繳憑單）")
        lines.append("")
        inc_gross = sum((i.amount for i in incomes), Decimal(0))
        slip_gross = sum((s.gross_amount for s in slips), Decimal(0))
        diff = inc_gross - slip_gross
        if abs(diff) > 0:
            sign = "多" if diff > 0 else "少"
            lines.append(
                f"- ⚠️ Income 合計 {_fmt(inc_gross)}，扣繳憑單合計 {_fmt(slip_gross)}，"
                f"Income {sign} {_fmt(abs(diff))}。"
            )
            if diff > 0:
                lines.append(
                    "  - 可能原因：業主未開扣繳憑單（給付 < 2 萬免開）、或 MyData 尚未更新。"
                )
            else:
                lines.append("  - 可能原因：Income 漏登某筆業主給付。請交叉核對。")
        else:
            lines.append(f"- ✅ Income 合計與扣繳憑單合計一致（{_fmt(inc_gross)}）。")
        lines.append("")

    # ---- 試算結果 ----
    lines.append("## 三、稅額試算")
    lines.append("")
    lines.append("| 項目 | 金額 |")
    lines.append("|---|---:|")
    lines.append(f"| 薪資所得（50）毛額 | {_fmt(tr.income_50_total)} |")
    if tr.income_9a_total:
        lines.append(f"| 執行業務 9A 毛額 | {_fmt(tr.income_9a_total)} |")
    if tr.income_9b_author_total:
        lines.append(f"| 稿費 9B_author 毛額 | {_fmt(tr.income_9b_author_total)} |")
    if tr.income_9b_speech_total:
        lines.append(f"| 講演 9B_speech 毛額 | {_fmt(tr.income_9b_speech_total)} |")
    if tr.income_9b_other_total:
        lines.append(f"| 其他 9B_other 毛額 | {_fmt(tr.income_9b_other_total)} |")
    if tr.income_92_total:
        lines.append(f"| 其他所得 92 | {_fmt(tr.income_92_total)} |")
    lines.append(f"| 執業所得（扣費用率後）應稅 | {_fmt(tr.execution_taxable)} |")
    lines.append(f"| **綜合所得總額** | **{_fmt(tr.gross_income)}** |")
    lines.append(f"| − 免稅額（{1 + int(is_married) + dependents} 人） | {_fmt(tr.exemption)} |")
    if tr.standard_deduction:
        lines.append(f"| − 標準扣除額 | {_fmt(tr.standard_deduction)} |")
    else:
        lines.append(f"| − 列舉扣除額 | {_fmt(tr.itemized_deduction)} |")
    lines.append(f"| − 薪資所得特別扣除額 | {_fmt(tr.salary_special_deduction)} |")
    lines.append(f"| **綜合所得淨額** | **{_fmt(tr.taxable_income)}** |")
    lines.append(f"| 適用稅率 | {tr.tax_rate*100:.0f}% |")
    lines.append(f"| 累進差額 | {_fmt(tr.progressive_deduction)} |")
    lines.append(f"| **應納稅額** | **{_fmt(tr.tax_payable)}** |")
    lines.append("")

    lines.append("### 退/補")
    lines.append("")
    lines.append("| 項目 | 金額 |")
    lines.append("|---|---:|")
    lines.append(f"| 應納稅額 | {_fmt(tr.tax_payable)} |")
    lines.append(f"| − 已扣繳綜所稅（合計） | {_fmt(tr.total_tax_withheld)} |")
    refund = tr.tax_owed_or_refund
    if refund > 0:
        lines.append(f"| **= 應補繳** | **{_fmt(refund)}** |")
    elif refund < 0:
        lines.append(f"| **= 可退稅** | **{_fmt(-refund)}** |")
    else:
        lines.append("| = 剛好打平 | 0 |")
    lines.append("")
    lines.append(
        f"> 本年度已被業主扣繳二代健保補充保費合計：{_fmt(tr.total_nhi_withheld)}"
        "（不影響綜所稅，僅供對帳）"
    )
    lines.append("")

    # ---- 系統說明 ----
    if tr.notes:
        lines.append("### 系統試算說明")
        lines.append("")
        for n in tr.notes:
            lines.append(f"- {n}")
        lines.append("")

    # ---- 5 月填報提醒 ----
    lines.append("## 四、填報步驟建議")
    lines.append("")
    lines.append("1. 到 MyData / 綜所稅電子申報系統下載年度扣繳清單。")
    lines.append("2. 與上面第二段表格比對，找出差異。")
    lines.append("3. 到財政部電子申報系統逐筆輸入（系統會自動帶扣繳）。")
    lines.append("4. 扣除額若改列舉，請把所有收據備妥。")
    lines.append("5. 提交前再看一次「應納稅額 vs 已扣繳」數字。")
    lines.append("")

    return "\n".join(lines)
