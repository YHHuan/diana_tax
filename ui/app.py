"""
Diana Tax — 主程式入口

啟動方式：
    streamlit run ui/app.py

或雙擊 start.command (Mac) / start.bat (Windows)
"""

import sys
from pathlib import Path

# 確保能 import core, storage
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from datetime import date
from decimal import Decimal

from storage.db import init_db, list_incomes, get_settings
from core import rules_114 as R
from core.tax_engine import calculate_annual_tax


# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="Diana Tax | 記帳報稅助手",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化 DB
init_db()


# ============================================================
# Header
# ============================================================
st.title("💰 Diana Tax — 記帳報稅助手")
st.caption(f"台灣自由工作者綜所稅管理 · {R.TAX_YEAR} 年度（{R.FILING_YEAR_AD}/5 申報）")


# ============================================================
# Sidebar — 導覽
# ============================================================
with st.sidebar:
    st.markdown("### 功能")
    st.markdown("""
    - 📊 **首頁 Dashboard** — 本年度總覽
    - ➕ **新增收入** — 快速記一筆
    - 📋 **收入明細** — 表格檢視 / 編輯
    - 🧮 **稅額試算** — 年度 / 情境試算
    - 👤 **個人設定** — 婚姻、職業、扶養
    - 📤 **匯入 / 匯出** — 銀行 CSV、扣繳憑單
    """)
    st.divider()
    st.caption("v0 - 2026/04")


# ============================================================
# 主 Dashboard
# ============================================================

incomes = list_incomes(tax_year=R.TAX_YEAR)
settings = get_settings()

# ---- 頂部 KPI ----
col1, col2, col3, col4 = st.columns(4)

total_gross = sum((inc.amount for inc in incomes), Decimal(0))
total_tax_withheld = sum((inc.tax_withheld for inc in incomes), Decimal(0))
total_nhi_withheld = sum((inc.nhi_withheld for inc in incomes), Decimal(0))

# 試算年度稅額
income_dicts = [{'amount': inc.amount, 'income_type': inc.income_type} for inc in incomes]
tax_result = calculate_annual_tax(
    incomes=income_dicts,
    is_married=settings.is_married,
    dependents=settings.dependents,
    has_elderly_dependent=settings.has_elderly_dependent,
    occupation=settings.occupation,
)
tax_result.total_tax_withheld = total_tax_withheld
tax_result.total_nhi_withheld = total_nhi_withheld
tax_result.tax_owed_or_refund = tax_result.tax_payable - total_tax_withheld

with col1:
    st.metric("本年度收入（毛額）", f"NT$ {int(total_gross):,}")
with col2:
    st.metric("已被扣繳（綜所稅）", f"NT$ {int(total_tax_withheld):,}")
with col3:
    st.metric("已被扣繳（二代健保）", f"NT$ {int(total_nhi_withheld):,}")
with col4:
    refund_or_owe = tax_result.tax_owed_or_refund
    if refund_or_owe > 0:
        st.metric("預估應補繳", f"NT$ {int(refund_or_owe):,}", delta="補稅", delta_color="inverse")
    else:
        st.metric("預估可退稅", f"NT$ {int(-refund_or_owe):,}", delta="退稅", delta_color="normal")

st.divider()


# ---- 稅額試算細節 ----
with st.expander("🧮 本年度綜所稅試算細節", expanded=True):
    cc1, cc2 = st.columns(2)

    with cc1:
        st.markdown("**收入組成**")
        rows = []
        if tax_result.income_50_total > 0:
            rows.append(("薪資所得 (50)", int(tax_result.income_50_total)))
        if tax_result.income_9a_total > 0:
            rows.append(("執業所得 9A", int(tax_result.income_9a_total)))
        if tax_result.income_9b_author_total > 0:
            rows.append(("稿費/版稅 (9B)", int(tax_result.income_9b_author_total)))
        if tax_result.income_9b_speech_total > 0:
            rows.append(("講演鐘點費 (9B)", int(tax_result.income_9b_speech_total)))
        if tax_result.income_9b_other_total > 0:
            rows.append(("其他執業 9B", int(tax_result.income_9b_other_total)))
        if tax_result.income_92_total > 0:
            rows.append(("其他所得 (92)", int(tax_result.income_92_total)))
        if rows:
            for label, v in rows:
                st.text(f"{label}: NT$ {v:,}")
        else:
            st.info("還沒有任何收入紀錄 — 從「新增收入」開始")

    with cc2:
        st.markdown("**稅額計算**")
        st.text(f"綜合所得總額: NT$ {int(tax_result.gross_income):,}")
        st.text(f"− 免稅額: NT$ {int(tax_result.exemption):,}")
        if tax_result.standard_deduction > 0:
            st.text(f"− 標準扣除額: NT$ {int(tax_result.standard_deduction):,}")
        else:
            st.text(f"− 列舉扣除額: NT$ {int(tax_result.itemized_deduction):,}")
        st.text(f"− 薪資特別扣除: NT$ {int(tax_result.salary_special_deduction):,}")
        st.text(f"= 應稅所得淨額: NT$ {int(tax_result.taxable_income):,}")
        st.text(f"適用稅率: {tax_result.tax_rate*100:.0f}%")
        st.text(f"應納稅額: NT$ {int(tax_result.tax_payable):,}")

    if tax_result.notes:
        st.markdown("**說明**")
        for note in tax_result.notes:
            st.caption(f"• {note}")


st.divider()


# ---- 近期收入 ----
st.subheader("📋 近期收入")

if not incomes:
    st.info("還沒有收入紀錄。左側選「➕ 新增收入」開始填第一筆。")
else:
    # 顯示前 10 筆
    import pandas as pd
    df = pd.DataFrame([
        {
            '日期': inc.date,
            '案主ID': str(inc.client_id)[:8] if inc.client_id else '',
            '金額': f"NT$ {int(inc.amount):,}",
            '類型': R.INCOME_TYPE_LABELS_ZH.get(inc.income_type, inc.income_type),
            '扣繳綜所稅': f"NT$ {int(inc.tax_withheld):,}",
            '扣繳二代健保': f"NT$ {int(inc.nhi_withheld):,}",
            '狀態': inc.status,
        }
        for inc in incomes[:10]
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    if len(incomes) > 10:
        st.caption(f"只顯示前 10 筆，共 {len(incomes)} 筆。請到「📋 收入明細」頁查看全部。")


st.divider()


# ---- Footer ----
st.caption(
    "⚠️ 本工具僅為試算參考，不構成稅務諮詢。"
    "實際申報請以財政部官方系統為準。"
    "稅額計算涵蓋 114 年度綜所稅參數，資料來源為財政部賦稅署公告。"
)
