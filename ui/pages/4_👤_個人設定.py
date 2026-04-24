"""
個人設定頁 — 影響稅額計算的個人狀態
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from storage.db import get_settings, update_settings
from core import rules_114 as R


st.set_page_config(page_title="個人設定", page_icon="👤", layout="wide")
st.title("👤 個人設定")

settings = get_settings()

with st.form("settings_form"):
    st.subheader("基本資料")
    name = st.text_input("名字", value=settings.name, placeholder="選填，只顯示在 Dashboard")

    st.subheader("家庭狀況（影響免稅額）")
    c1, c2, c3 = st.columns(3)
    with c1:
        is_married = st.checkbox("已婚（合併申報）", value=settings.is_married)
    with c2:
        dependents = st.number_input("扶養親屬人數", min_value=0, max_value=20, value=settings.dependents)
    with c3:
        has_elderly = st.checkbox("其中有 70+ 直系尊親屬", value=settings.has_elderly_dependent)

    st.caption(
        f"💡 本人免稅額 {R.EXEMPTION_PER_PERSON:,} + 每位扶養親屬 {R.EXEMPTION_PER_PERSON:,}（70+ 為 {R.EXEMPTION_ELDERLY:,}）"
    )

    st.subheader("職業類別（影響 9A / 9B 費用率）")
    occupation_options = list(R.EXPENSE_RATES.keys())
    occupation = st.selectbox(
        "主要職業",
        options=occupation_options,
        index=occupation_options.index(settings.occupation) if settings.occupation in occupation_options else 0,
        format_func=lambda x: f"{R.OCCUPATION_LABELS_ZH.get(x, x)} — 費用率 {R.EXPENSE_RATES[x]*100:.0f}%",
    )
    st.caption(
        "依財政部 113 年度執行業務者費用標準。不確定選 default（30%）。"
        "自行出版的著作人可以選「著作人（自行出版）」享 75% 費用率。"
    )

    st.subheader("健保狀態（影響二代健保扣繳）")
    nhi_type = st.selectbox(
        "健保投保方式",
        options=["union", "employer", "other"],
        index=["union", "employer", "other"].index(settings.nhi_insurance_type),
        format_func=lambda x: {"union": "職業工會", "employer": "公司投保", "other": "其他"}[x],
    )
    has_regular_job = st.checkbox("我有正職（業主可能不扣 10% 綜所稅）", value=settings.has_regular_job)

    st.subheader("扣除額模式")
    deduction_mode = st.radio(
        "預設使用",
        options=["standard", "itemized"],
        index=0 if settings.deduction_mode == "standard" else 1,
        format_func=lambda x: f"標準扣除額（{R.STANDARD_DEDUCTION_SINGLE:,}/{R.STANDARD_DEDUCTION_MARRIED:,}）" if x == "standard" else "列舉扣除額",
    )

    if st.form_submit_button("💾 儲存設定", type="primary"):
        settings.name = name
        settings.is_married = is_married
        settings.dependents = dependents
        settings.has_elderly_dependent = has_elderly
        settings.occupation = occupation
        settings.nhi_insurance_type = nhi_type
        settings.has_regular_job = has_regular_job
        settings.deduction_mode = deduction_mode
        update_settings(settings)
        st.success("✅ 已儲存")


st.divider()

# 法規資訊
with st.expander("📖 114 年度綜所稅參數（唯讀）"):
    st.markdown(f"""
    - **免稅額**：每人 NT$ {R.EXEMPTION_PER_PERSON:,}（70+ NT$ {R.EXEMPTION_ELDERLY:,}）
    - **標準扣除額**：單身 NT$ {R.STANDARD_DEDUCTION_SINGLE:,} / 有配偶 NT$ {R.STANDARD_DEDUCTION_MARRIED:,}
    - **薪資特別扣除額**：NT$ {R.SALARY_SPECIAL_DEDUCTION:,}
    - **基本生活費**：NT$ {R.BASIC_LIVING_COST:,} / 人
    - **稿費免稅額**：年度合計 NT$ {R.AUTHOR_TAX_FREE_LIMIT:,} 以下免稅
    - **二代健保費率**：{R.NHI_SUPPLEMENTARY_RATE*100:.2f}%
    - **二代健保 9A/9B 單筆起扣**：NT$ {R.NHI_THRESHOLD_9A_9B:,}
    - **二代健保兼職起扣**：NT$ {R.NHI_THRESHOLD_PART_TIME:,}

    **課稅級距**：
    """)
    for upper, rate, deduct in R.TAX_BRACKETS:
        upper_str = "∞" if upper == float('inf') else f"{int(upper):,}"
        st.markdown(f"- ≤ NT$ {upper_str} × {rate*100:.0f}% − {int(deduct):,}")
