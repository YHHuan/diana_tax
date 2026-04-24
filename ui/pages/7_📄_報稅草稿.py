"""
報稅草稿頁 — 一鍵產出 Markdown，Diana 5 月對著財政部官方軟體填。
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date
from decimal import Decimal

import streamlit as st
from sqlmodel import select

from storage.db import get_session, get_settings, list_incomes
from core.models import WithholdingSlip, Client
from core.report import build_markdown_report, IncomeRow, SlipRow
from core.report_pdf import PdfExportUnavailable, render_markdown_pdf
from core import rules_114 as R


st.set_page_config(page_title="報稅草稿 | Diana Tax", page_icon="📄", layout="wide")
st.title("📄 報稅草稿")
st.caption("一鍵產出 Markdown 報稅草稿，5 月對著財政部電子申報系統填")

settings = get_settings()

c1, c2, c3 = st.columns(3)
with c1:
    tax_year = st.selectbox(
        "稅年度",
        options=[114, 115],
        index=0,
    )
with c2:
    include_draft_preview = st.checkbox("含明細表格", value=True)
with c3:
    use_itemized = st.checkbox("改用列舉扣除額", value=(settings.deduction_mode == "itemized"))

itemized_amount: Decimal | None = None
if use_itemized:
    itemized_amount = Decimal(str(st.number_input(
        "列舉扣除額合計（NT$）",
        min_value=0,
        value=0,
        step=1000,
        help="保險、醫療、捐贈、購屋借款利息等合計",
    )))

# ---- 拉資料 ----
incomes_db = list_incomes(tax_year=tax_year)

# client id → name map
with get_session() as s:
    client_rows = list(s.exec(select(Client)))
    client_name_by_id = {c.id: c.name for c in client_rows}

    slip_rows_db = list(s.exec(
        select(WithholdingSlip).where(WithholdingSlip.tax_year == tax_year)
    ))

income_rows = [
    IncomeRow(
        date=inc.date,
        payer_name=client_name_by_id.get(inc.client_id, "") if inc.client_id else "",
        amount=inc.amount,
        income_type=inc.income_type,
        tax_withheld=inc.tax_withheld,
        nhi_withheld=inc.nhi_withheld,
    )
    for inc in incomes_db
]
slip_rows = [
    SlipRow(
        payer_name=s.payer_name,
        payer_tax_id=s.payer_tax_id,
        income_type=s.income_type,
        gross_amount=s.gross_amount,
        tax_withheld=s.tax_withheld,
        nhi_withheld=s.nhi_withheld,
    )
    for s in slip_rows_db
]

st.caption(f"已找到：{len(income_rows)} 筆收入、{len(slip_rows)} 張扣繳憑單")

if not income_rows and not slip_rows:
    st.info("本年度尚無資料。先到「新增收入」或「匯入匯出」登錄資料。")
    st.stop()

# ---- 產出 ----
md = build_markdown_report(
    tax_year=tax_year,
    incomes=income_rows,
    slips=slip_rows,
    is_married=settings.is_married,
    dependents=settings.dependents,
    has_elderly_dependent=settings.has_elderly_dependent,
    occupation=settings.occupation,
    itemized_deduction=itemized_amount,
    user_name=settings.name,
)

download_col_1, download_col_2 = st.columns(2)
with download_col_1:
    st.download_button(
        "⬇️ 下載 Markdown 草稿",
        data=md.encode("utf-8"),
        file_name=f"diana_tax_draft_{tax_year}.md",
        mime="text/markdown",
        type="primary",
    )
with download_col_2:
    try:
        pdf_bytes = render_markdown_pdf(md, title=f"{tax_year} 年度綜所稅申報草稿")
    except PdfExportUnavailable as exc:
        st.info(str(exc))
    else:
        st.download_button(
            "⬇️ 下載 PDF 草稿",
            data=pdf_bytes,
            file_name=f"diana_tax_draft_{tax_year}.pdf",
            mime="application/pdf",
        )

st.divider()
if include_draft_preview:
    st.markdown(md)
else:
    with st.expander("展開完整 Markdown 預覽"):
        st.markdown(md)
