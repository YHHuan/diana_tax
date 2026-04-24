"""
新增收入頁 — Diana 每週/每月進來記一筆
設計：最小摩擦，3 個必填，其他都可後補
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from datetime import date
from decimal import Decimal

from storage.db import save_income, list_clients, save_client, list_projects, get_settings
from core.models import Income, Client, Project
from core.tax_engine import classify_single_income
from core import rules_114 as R


st.set_page_config(page_title="新增收入", page_icon="➕", layout="wide")
st.title("➕ 新增收入")

settings = get_settings()
clients = list_clients()
projects = list_projects()

# ============================================================
# 主表單
# ============================================================

with st.form("new_income", clear_on_submit=False):
    st.subheader("必填")
    c1, c2, c3 = st.columns(3)

    with c1:
        inc_date = st.date_input("發生日 *", value=date.today(), help="業主給付日 / 發票日")
    with c2:
        amount = st.number_input("金額 (NT$) *", min_value=0, step=1000, value=0)
    with c3:
        income_type = st.selectbox(
            "所得類別 *",
            options=list(R.INCOME_TYPE_LABELS_ZH.keys()),
            format_func=lambda x: R.INCOME_TYPE_LABELS_ZH[x],
            index=3,  # 預設 9B_other
            help="不確定？hover 看每個類別說明"
        )
        st.caption(R.INCOME_TYPE_DESCRIPTIONS.get(income_type, ""))

    st.markdown("---")
    st.subheader("選填")

    c4, c5 = st.columns(2)
    with c4:
        client_options = {c.name: c.id for c in clients}
        client_options["（新增新案主）"] = None
        client_options["（不指定）"] = "none"
        client_choice = st.selectbox("案主", options=list(client_options.keys()))

        new_client_name = ""
        if client_choice == "（新增新案主）":
            new_client_name = st.text_input("新案主名稱")

    with c5:
        project_choice = st.selectbox(
            "專案",
            options=["（不指定）"] + [p.name for p in projects]
        )

    c6, c7, c8 = st.columns(3)
    with c6:
        status = st.selectbox("狀態", ["invoiced", "received", "overdue"], index=1,
                              format_func=lambda x: {"invoiced": "已開單/已出", "received": "已入帳", "overdue": "逾期未付"}[x])
    with c7:
        received_date = st.date_input("入帳日（如已入帳）", value=None)
    with c8:
        pass

    # 扣繳資訊
    st.markdown("---")
    st.subheader("扣繳（業主已扣多少）")

    # 智能預測
    if amount > 0:
        expected = classify_single_income(
            amount=Decimal(str(amount)),
            income_type=income_type,
            occupation=settings.occupation,
        )
        if expected.expected_tax_withheld > 0 or expected.expected_nhi_withheld > 0:
            st.info(
                f"💡 依規定業主應扣繳：綜所稅 NT$ {int(expected.expected_tax_withheld):,}，"
                f"二代健保 NT$ {int(expected.expected_nhi_withheld):,}"
            )
        for note in expected.notes:
            st.caption(f"• {note}")

    c9, c10 = st.columns(2)
    with c9:
        tax_withheld = st.number_input("扣繳綜所稅 (NT$)", min_value=0, step=100, value=0)
    with c10:
        nhi_withheld = st.number_input("扣繳二代健保 (NT$)", min_value=0, step=10, value=0)

    st.markdown("---")
    notes = st.text_area("備註", placeholder="這筆錢的背景、發票號碼、匯款截圖描述...")

    submitted = st.form_submit_button("💾 儲存", type="primary", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.error("金額要大於 0")
            st.stop()

        # 處理案主
        client_id = None
        if client_choice == "（新增新案主）":
            if new_client_name.strip():
                new_c = save_client(Client(name=new_client_name.strip()))
                client_id = new_c.id
            else:
                st.error("要填新案主名稱")
                st.stop()
        elif client_choice not in ("（不指定）",):
            client_id = client_options.get(client_choice)

        inc = Income(
            date=inc_date,
            amount=Decimal(str(amount)),
            income_type=income_type,
            tax_withheld=Decimal(str(tax_withheld)),
            nhi_withheld=Decimal(str(nhi_withheld)),
            client_id=client_id,
            status=status,
            received_date=received_date,
            notes=notes,
            tax_year=R.TAX_YEAR,
        )
        save_income(inc)
        st.success(f"✅ 已記錄 NT$ {amount:,.0f} ({R.INCOME_TYPE_LABELS_ZH[income_type]})")
        st.balloons()


# ============================================================
# 小工具：LLM 粘貼助手（v1 功能預告）
# ============================================================

with st.expander("🤖 LLM 解析（v1 功能預告）"):
    st.caption("未來可貼業主 email、匯款截圖、扣繳憑單 PDF，AI 自動填表")
    st.text_area(
        "貼一段業主 email / 匯款通知",
        placeholder="例：「您好，本月講座費用 30,000 元已於 4/20 匯入您的帳戶，已扣繳稅額 3,000 元，二代健保補充保費 633 元。發票請開立講師鐘點費，謝謝。」",
        key="llm_input",
        disabled=True,
    )
    st.button("✨ 解析（v1 將啟用）", disabled=True)
