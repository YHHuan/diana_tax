"""
收入明細頁 — Excel-like 表格
- 可排序、篩選
- 可批次編輯
- 可匯出 CSV
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from datetime import date
from decimal import Decimal
from io import StringIO

from storage.db import list_incomes, list_clients, get_session, delete_income
from core.models import Income
from core import rules_114 as R


st.set_page_config(page_title="收入明細", page_icon="📋", layout="wide")
st.title("📋 收入明細")


# ============================================================
# Filters
# ============================================================
c1, c2, c3 = st.columns(3)
with c1:
    tax_year = st.selectbox("稅年度", [R.TAX_YEAR, R.TAX_YEAR - 1], index=0)
with c2:
    type_filter = st.multiselect(
        "所得類別（空白=全部）",
        options=list(R.INCOME_TYPE_LABELS_ZH.keys()),
        format_func=lambda x: R.INCOME_TYPE_LABELS_ZH[x],
    )
with c3:
    status_filter = st.multiselect(
        "狀態（空白=全部）",
        options=["invoiced", "received", "overdue", "cancelled"],
    )


# ============================================================
# Data
# ============================================================
incomes = list_incomes(tax_year=tax_year, limit=1000)

if type_filter:
    incomes = [i for i in incomes if i.income_type in type_filter]
if status_filter:
    incomes = [i for i in incomes if i.status in status_filter]

clients = {c.id: c.name for c in list_clients()}


# ============================================================
# Summary
# ============================================================
total = sum((i.amount for i in incomes), Decimal(0))
n = len(incomes)
st.caption(f"共 **{n}** 筆，合計 **NT$ {int(total):,}**")


# ============================================================
# Table
# ============================================================
if not incomes:
    st.info("沒有符合條件的收入紀錄")
else:
    df = pd.DataFrame([
        {
            'ID': str(inc.id)[:8],
            '日期': inc.date,
            '案主': clients.get(inc.client_id, '—'),
            '金額': int(inc.amount),
            '類別': R.INCOME_TYPE_LABELS_ZH.get(inc.income_type, inc.income_type),
            '類別_code': inc.income_type,
            '扣繳綜所稅': int(inc.tax_withheld),
            '扣繳二代健保': int(inc.nhi_withheld),
            '狀態': inc.status,
            '入帳日': inc.received_date,
            '備註': inc.notes,
            '_id': str(inc.id),
        }
        for inc in incomes
    ])

    # 顯示用的 columns
    display_cols = ['日期', '案主', '金額', '類別', '扣繳綜所稅', '扣繳二代健保', '狀態', '入帳日', '備註']

    edited = st.data_editor(
        df[display_cols + ['_id']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "_id": None,  # 隱藏
            "金額": st.column_config.NumberColumn(format="$%d"),
            "扣繳綜所稅": st.column_config.NumberColumn(format="$%d"),
            "扣繳二代健保": st.column_config.NumberColumn(format="$%d"),
        },
        disabled=['日期', '案主', '金額', '類別', '扣繳綜所稅', '扣繳二代健保'],  # 只允許改狀態、入帳日、備註
        num_rows="fixed",
    )

    st.caption("💡 可以直接在表格上編輯「狀態」「入帳日」「備註」欄位")


# ============================================================
# Actions
# ============================================================
st.divider()

c1, c2 = st.columns(2)
with c1:
    if incomes:
        # 匯出 CSV
        csv_df = pd.DataFrame([
            {
                '日期': inc.date.isoformat(),
                '案主': clients.get(inc.client_id, ''),
                '金額': int(inc.amount),
                '所得類別': inc.income_type,
                '所得類別名稱': R.INCOME_TYPE_LABELS_ZH.get(inc.income_type, ''),
                '扣繳綜所稅': int(inc.tax_withheld),
                '扣繳二代健保': int(inc.nhi_withheld),
                '狀態': inc.status,
                '入帳日': inc.received_date.isoformat() if inc.received_date else '',
                '備註': inc.notes or '',
            }
            for inc in incomes
        ])
        csv = csv_df.to_csv(index=False).encode('utf-8-sig')  # UTF-8 BOM for Excel 中文
        st.download_button(
            "📤 下載 CSV（可 Excel 打開）",
            data=csv,
            file_name=f"diana_incomes_{tax_year}.csv",
            mime="text/csv",
        )

with c2:
    with st.expander("🗑️ 刪除某筆"):
        if incomes:
            to_delete = st.selectbox(
                "選擇要刪除的收入",
                options=[(str(inc.id), f"{inc.date} | NT$ {int(inc.amount):,} | {R.INCOME_TYPE_LABELS_ZH.get(inc.income_type)}") for inc in incomes],
                format_func=lambda x: x[1],
            )
            if st.button("確認刪除", type="secondary"):
                delete_income(to_delete[0])
                st.success("已刪除")
                st.rerun()
