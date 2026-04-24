"""
應收未收追蹤 — pure function, 沒有 DB 依賴。

設計：
- 接一個 list[IncomeLite] 和 today → 回 list[ReceivableStatus]
- 每筆標註：days_outstanding, is_overdue, suggested_action
- 門檻：預設 30 天；UI 層可改

status 規則：
- status='received'            → 不在 receivable 清單裡
- status='invoiced' 且 <30d    → pending
- status='invoiced' 且 ≥30d    → overdue
- status='overdue'             → 已標記 overdue
- status='cancelled'           → 排除
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Optional


@dataclass
class IncomeLite:
    """對外 API — 簡化版 Income，給 core.receivables 吃"""
    id: str
    date: date
    amount: Decimal
    currency: str = "TWD"
    payer_name: str = ""
    status: str = "invoiced"
    received_date: Optional[date] = None
    notes: str = ""


@dataclass
class ReceivableStatus:
    income: IncomeLite
    days_outstanding: int
    is_overdue: bool
    category: str  # pending / overdue_soft / overdue_hard
    suggested_action: str


def classify_receivables(
    incomes: Iterable[IncomeLite],
    today: Optional[date] = None,
    overdue_threshold_days: int = 30,
    hard_threshold_days: int = 60,
) -> list[ReceivableStatus]:
    """
    Return receivables sorted by most-overdue first.
    'pending': invoiced 但還沒到門檻
    'overdue_soft': 過 threshold 但沒過 hard
    'overdue_hard': 過 hard，要動了
    """
    today = today or date.today()
    out: list[ReceivableStatus] = []
    for inc in incomes:
        if inc.status in ("received", "cancelled"):
            continue
        days = (today - inc.date).days
        if days < overdue_threshold_days:
            cat = "pending"
            action = f"尚未到門檻（{overdue_threshold_days}d），再觀察"
        elif days < hard_threshold_days:
            cat = "overdue_soft"
            action = "寄一封客氣的提醒 email / LINE"
        else:
            cat = "overdue_hard"
            action = "第二次追款：電話或要求對帳單"
        out.append(ReceivableStatus(
            income=inc,
            days_outstanding=days,
            is_overdue=days >= overdue_threshold_days,
            category=cat,
            suggested_action=action,
        ))
    # 最久沒收到的排最前
    out.sort(key=lambda r: r.days_outstanding, reverse=True)
    return out


# ============================================================
# 催款文字生成（local fallback — 不用 LLM 也能用）
# LLM 版在 importers/llm/dunning.py 有更聰明的版本
# ============================================================

def draft_dunning_text_simple(
    payer_name: str,
    amount: Decimal,
    invoice_date: date,
    days_outstanding: int,
    tone: str = "polite",
    language: str = "zh-TW",
) -> str:
    """
    極簡中文催款草稿。LLM 版可以吃更多 context (之前信件往返、合約條款)，
    但 local fallback 先能用。
    """
    pn = payer_name or "[業主]"
    amount_str = f"NT$ {int(amount):,}"
    date_str = invoice_date.isoformat()

    if tone == "polite":
        return (
            f"{pn} 您好，想跟您確認一下：\n\n"
            f"我於 {date_str} 提供的服務，金額 {amount_str}，"
            f"到目前（{days_outstanding} 天）尚未收到匯款。\n"
            f"是否方便協助查看一下付款進度？若有需要補開收據或調整對帳資料，再請告知。\n\n"
            f"謝謝您！\n"
        )
    elif tone == "firm":
        return (
            f"{pn} 您好，關於 {date_str} 的服務費 {amount_str}，"
            f"已 {days_outstanding} 天未收到款項。\n"
            f"煩請於本週內處理匯款，或回覆預定付款時間，以利雙方作業。\n\n"
            f"若您這邊對金額或合約有任何疑問，歡迎直接與我聯絡。\n\n"
            f"感謝。\n"
        )
    else:  # neutral
        return (
            f"{pn} 您好，\n\n"
            f"提醒一下 {date_str} 之服務款項（{amount_str}）"
            f"目前已逾 {days_outstanding} 天未收。請協助確認。\n\n"
            f"謝謝。\n"
        )
