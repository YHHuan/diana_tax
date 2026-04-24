"""
應收追蹤頁 — 哪些案主還沒匯款、逾期多久、一鍵產出催款文字。
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlmodel import select

from storage.db import get_session, list_incomes
from core.models import Client, Income
from core.receivables import (
    IncomeLite,
    classify_receivables,
    draft_dunning_text_simple,
)
from core import rules_114 as R


st.set_page_config(page_title="應收追蹤 | Diana Tax", page_icon="⏰", layout="wide")
st.title("⏰ 應收追蹤")
st.caption("逾期未收款 + 一鍵催款文字草稿")

# ---- 設定 ----
c1, c2, c3 = st.columns(3)
with c1:
    threshold_days = st.number_input("軟逾期門檻（天）", min_value=7, max_value=180, value=30, step=1)
with c2:
    hard_days = st.number_input("硬逾期門檻（天）", min_value=14, max_value=365, value=60, step=1)
with c3:
    tax_year = st.selectbox("稅年度", options=[114, 115], index=0)

# ---- 讀 DB ----
incomes_db = list_incomes(tax_year=tax_year)
with get_session() as s:
    client_rows = list(s.exec(select(Client)))
    name_by_id = {c.id: c.name for c in client_rows}

lites = [
    IncomeLite(
        id=str(inc.id),
        date=inc.date,
        amount=inc.amount,
        currency=inc.currency,
        payer_name=name_by_id.get(inc.client_id, "") if inc.client_id else "",
        status=inc.status,
        received_date=inc.received_date,
        notes=inc.notes or "",
    )
    for inc in incomes_db
]

statuses = classify_receivables(
    lites,
    overdue_threshold_days=int(threshold_days),
    hard_threshold_days=int(hard_days),
)

# ---- Summary KPI ----
pending = [s for s in statuses if s.category == "pending"]
soft = [s for s in statuses if s.category == "overdue_soft"]
hard = [s for s in statuses if s.category == "overdue_hard"]

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("觀察中（未到門檻）", f"{len(pending)} 筆")
with k2:
    st.metric("軟逾期", f"{len(soft)} 筆", delta=f"≥ {threshold_days}d", delta_color="off")
with k3:
    st.metric("硬逾期（要動）", f"{len(hard)} 筆", delta=f"≥ {hard_days}d", delta_color="inverse")
with k4:
    total_owe = sum((s.income.amount for s in soft + hard), Decimal(0))
    st.metric("逾期金額", f"NT$ {int(total_owe):,}")

st.divider()

if not statuses:
    st.success("🎉 沒有待收款。該收的都收到了。")
    st.stop()

# ---- 表格 ----
rows = [
    {
        "選": False,
        "日期": s.income.date,
        "已逾天": s.days_outstanding,
        "業主": s.income.payer_name or "—",
        "金額": f"NT$ {int(s.income.amount):,}",
        "狀態": s.category,
        "建議": s.suggested_action,
        "_id": s.income.id,
    }
    for s in statuses
]
df = pd.DataFrame(rows)

# Colour hint: highlight hard-overdue
def _row_colour(row):
    if row["狀態"] == "overdue_hard":
        return ["background-color: #ffe5e5"] * len(row)
    if row["狀態"] == "overdue_soft":
        return ["background-color: #fff7e5"] * len(row)
    return [""] * len(row)

edited = st.data_editor(
    df.drop(columns=["_id"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "選": st.column_config.CheckboxColumn("選", help="勾選要產出催款文字"),
    },
    disabled=["日期", "已逾天", "業主", "金額", "狀態", "建議"],
    key="receivables_editor",
)

# Map edited back to statuses by index
selected_ix = [i for i, v in enumerate(edited["選"]) if v]
selected = [statuses[i] for i in selected_ix]

st.divider()

# ---- 動作區 ----
st.subheader("催款訊息草稿")

tone = st.segmented_control(
    "語氣",
    options=["polite", "firm", "neutral"],
    default="polite",
    format_func=lambda x: {"polite": "客氣", "firm": "直接", "neutral": "中性"}[x],
) if hasattr(st, "segmented_control") else st.radio(
    "語氣", options=["polite", "firm", "neutral"], horizontal=True,
)

use_llm = st.checkbox(
    "🤖 用 Claude 幫我寫（需 ANTHROPIC_API_KEY）",
    value=False,
    help="打開後會送業主名、金額、天數到 Claude API；未設定 key 時自動退回本地版本",
)
extra_context = st.text_area(
    "額外情境（非必填）",
    placeholder="例：這個業主第二次遲付、合約明載 Net 30...",
    height=80,
)

if not selected:
    st.info("勾一筆或多筆看草稿。")
    st.stop()

for i, s in enumerate(selected, 1):
    st.markdown(f"#### {i}. {s.income.payer_name or '—'}　（已逾 {s.days_outstanding} 天）")
    drafted = None
    err = None
    if use_llm:
        try:
            from importers.llm.dunning import draft_dunning_text_llm
            drafted = draft_dunning_text_llm(
                payer_name=s.income.payer_name or "[業主]",
                amount=s.income.amount,
                invoice_date=s.income.date,
                days_outstanding=s.days_outstanding,
                tone=tone,
                extra_context=extra_context.strip() or None,
            )
        except Exception as e:
            err = f"LLM 失敗，改用本地版：{e}"
    if drafted is None:
        drafted = draft_dunning_text_simple(
            payer_name=s.income.payer_name or "[業主]",
            amount=s.income.amount,
            invoice_date=s.income.date,
            days_outstanding=s.days_outstanding,
            tone=tone,
        )
    if err:
        st.warning(err)
    st.code(drafted, language=None)

st.divider()

# ---- Bulk 狀態更新 ----
st.subheader("標記為已收款")
col1, col2 = st.columns([3, 1])
with col1:
    received_date = st.date_input("收款日期", value=date.today())
with col2:
    if st.button("批次標記勾選項", type="primary", disabled=not selected):
        with get_session() as sess:
            for s in selected:
                inc = sess.get(Income, s.income.id) if False else None
                # SQLModel get by UUID needs real UUID; s.income.id is str
                from uuid import UUID
                try:
                    inc = sess.get(Income, UUID(s.income.id))
                except (ValueError, TypeError):
                    inc = None
                if inc is not None:
                    inc.status = "received"
                    inc.received_date = received_date
                    sess.add(inc)
            sess.commit()
        st.success(f"✅ 已標記 {len(selected)} 筆為收款。重整一下頁面。")
