"""
稅額試算頁 — 情境試算
- 現況 vs 假設
- 「如果我再接 X 元的案子」
- 「如果改成 9B 而非 50」
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from decimal import Decimal

from storage.db import list_incomes, get_settings
from core.tax_engine import calculate_annual_tax, classify_single_income
from core import rules_114 as R


st.set_page_config(page_title="稅額試算", page_icon="🧮", layout="wide")
st.title("🧮 稅額試算")


settings = get_settings()
existing_incomes = list_incomes(tax_year=R.TAX_YEAR)
existing_income_dicts = [{'amount': inc.amount, 'income_type': inc.income_type} for inc in existing_incomes]


# ============================================================
# Tab 1: 現況
# ============================================================
tab1, tab2, tab3 = st.tabs(["📊 本年度現況", "➕ 加一筆假設", "🔄 類別比較（9B vs 50）"])

with tab1:
    st.subheader(f"本年度（114）至今試算")

    current = calculate_annual_tax(
        incomes=existing_income_dicts,
        is_married=settings.is_married,
        dependents=settings.dependents,
        has_elderly_dependent=settings.has_elderly_dependent,
        occupation=settings.occupation,
    )
    total_withheld = sum((inc.tax_withheld for inc in existing_incomes), Decimal(0))
    current.total_tax_withheld = total_withheld
    current.tax_owed_or_refund = current.tax_payable - total_withheld

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("綜合所得總額", f"NT$ {int(current.gross_income):,}")
    with c2:
        st.metric("應納稅額", f"NT$ {int(current.tax_payable):,}")
    with c3:
        if current.tax_owed_or_refund > 0:
            st.metric("預估補繳", f"NT$ {int(current.tax_owed_or_refund):,}", delta="補稅", delta_color="inverse")
        else:
            st.metric("預估退稅", f"NT$ {int(-current.tax_owed_or_refund):,}", delta="退稅")

    with st.expander("詳細"):
        st.json(current.to_dict())


# ============================================================
# Tab 2: 加一筆假設
# ============================================================
with tab2:
    st.subheader("如果我再接這個案子...")
    st.caption("輸入一個假設收入，看看會變多少")

    c1, c2 = st.columns(2)
    with c1:
        hyp_amount = st.number_input("假設金額 (NT$)", min_value=0, step=10000, value=100_000)
    with c2:
        hyp_type = st.selectbox(
            "假設類別",
            options=list(R.INCOME_TYPE_LABELS_ZH.keys()),
            format_func=lambda x: R.INCOME_TYPE_LABELS_ZH[x],
            index=3,
        )

    # 比較
    new_incomes = existing_income_dicts + [{'amount': Decimal(str(hyp_amount)), 'income_type': hyp_type}]
    after = calculate_annual_tax(
        incomes=new_incomes,
        is_married=settings.is_married,
        dependents=settings.dependents,
        has_elderly_dependent=settings.has_elderly_dependent,
        occupation=settings.occupation,
    )

    delta_tax = after.tax_payable - current.tax_payable
    marginal_rate = float(delta_tax / Decimal(str(hyp_amount))) * 100 if hyp_amount > 0 else 0

    st.markdown("### 影響")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("新增所得", f"NT$ {hyp_amount:,}")
    with c2:
        st.metric("多繳稅", f"NT$ {int(delta_tax):,}")
    with c3:
        st.metric("有效邊際稅率", f"{marginal_rate:.2f}%")

    # 單筆被扣繳
    single = classify_single_income(
        amount=Decimal(str(hyp_amount)),
        income_type=hyp_type,
        occupation=settings.occupation,
    )
    if single.expected_tax_withheld or single.expected_nhi_withheld:
        st.info(
            f"💡 業主給付時會扣：綜所稅 NT$ {int(single.expected_tax_withheld):,}、"
            f"二代健保 NT$ {int(single.expected_nhi_withheld):,}。"
            f"實收 NT$ {int(Decimal(str(hyp_amount)) - single.expected_tax_withheld - single.expected_nhi_withheld):,}"
        )
    for note in single.notes:
        st.caption(f"• {note}")


# ============================================================
# Tab 3: 類別比較
# ============================================================
with tab3:
    st.subheader("同一筆金額，不同類別差多少？")
    st.caption("最常見：業主想開薪資（50）還是講演（9B），哪個對你比較划算？")

    amt = st.number_input("要比較的金額 (NT$)", min_value=0, step=10000, value=50_000)

    if amt > 0:
        types_to_compare = ['50', '9A', '9B_author', '9B_speech', '9B_other']
        results = []
        for t in types_to_compare:
            s = classify_single_income(
                amount=Decimal(str(amt)),
                income_type=t,
                occupation=settings.occupation,
            )
            net_received = Decimal(str(amt)) - s.expected_tax_withheld - s.expected_nhi_withheld

            # 併入年度計算估算邊際
            test_incomes = existing_income_dicts + [{'amount': Decimal(str(amt)), 'income_type': t}]
            test_result = calculate_annual_tax(
                incomes=test_incomes,
                is_married=settings.is_married,
                dependents=settings.dependents,
                has_elderly_dependent=settings.has_elderly_dependent,
                occupation=settings.occupation,
            )
            marginal = test_result.tax_payable - current.tax_payable

            results.append({
                '類別': R.INCOME_TYPE_LABELS_ZH[t],
                '業主扣繳綜所稅': int(s.expected_tax_withheld),
                '業主扣二代健保': int(s.expected_nhi_withheld),
                '當下實收': int(net_received),
                '年度多繳綜所稅': int(marginal),
                '最終實得': int(net_received - (marginal - s.expected_tax_withheld)),
            })

        import pandas as pd
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("「最終實得」= 實際到手 − 5月要補/加 退稅")
