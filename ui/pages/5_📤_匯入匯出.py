"""
匯入 / 匯出頁
- v0: CSV 匯入（她先手動整理）、JSON backup
- v1: 銀行 CSV parser、扣繳憑單 PDF OCR
- v2: MyData 整合
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd
from datetime import date
from decimal import Decimal
import json
from tempfile import NamedTemporaryFile

from storage.db import list_incomes, save_income, list_clients, save_client
from core.models import Income, Client
from core import rules_114 as R
from importers.bank_csv import parse as parse_bank_csv


st.set_page_config(page_title="匯入 / 匯出", page_icon="📤", layout="wide")
st.title("📤 匯入 / 匯出")

tab1, tab2, tab3, tab4 = st.tabs(["📥 CSV 匯入", "📦 JSON 備份/還原", "💾 匯出報稅草稿", "🔮 未來整合"])


# ============================================================
# Tab 1: CSV 匯入
# ============================================================
with tab1:
    # === 銀行 CSV ===
    st.subheader("銀行 CSV 匯入")
    st.caption("先把銀行入帳明細解析成草稿，再由 Diana 勾選、補所得類別後寫入正式收入。")

    bank_options = {
        "cathay": "國泰世華 MyB2B / CUBE",
        "esun": "玉山（先走 generic fallback）",
        "twb": "台銀（先走 generic fallback）",
        "wise": "Wise（先走 generic fallback）",
        "generic": "通用 3 欄 CSV",
    }
    income_type_options = [""] + list(R.INCOME_TYPE_LABELS_ZH.keys())

    selected_bank = st.selectbox(
        "銀行格式",
        options=list(bank_options.keys()),
        format_func=lambda key: bank_options[key],
        key="bank_csv_bank",
    )
    uploaded_bank_csv = st.file_uploader("上傳銀行 CSV", type=["csv"], key="bank_csv_uploader")

    if uploaded_bank_csv:
        tmp_path = None
        try:
            with NamedTemporaryFile("wb", suffix=".csv", delete=False) as handle:
                handle.write(uploaded_bank_csv.getvalue())
                tmp_path = Path(handle.name)
            drafts = parse_bank_csv(tmp_path, selected_bank)
        except Exception as e:
            st.error(f"銀行 CSV 解析失敗：{e}")
            drafts = []
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        if uploaded_bank_csv and drafts:
            preview_rows = []
            for draft in drafts:
                preview_rows.append({
                    "匯入": True,
                    "日期": draft.date.isoformat(),
                    "金額": str(draft.amount),
                    "所得類別": draft.suggested_income_type or "",
                    "扣繳綜所稅": "0",
                    "扣繳二代健保": "0",
                    "對方": draft.counterparty_hint or "",
                    "說明": draft.raw_description,
                    "備註": draft.notes,
                    "來源": draft.source,
                    "來源列": draft.source_row_id or "",
                    "信心": draft.confidence,
                })

            st.write("**銀行 CSV 草稿預覽**")
            edited_bank_df = st.data_editor(
                pd.DataFrame(preview_rows),
                hide_index=True,
                use_container_width=True,
                key=f"bank_csv_editor_{selected_bank}_{uploaded_bank_csv.name}",
                column_config={
                    "匯入": st.column_config.CheckboxColumn("匯入"),
                    "日期": st.column_config.TextColumn("日期"),
                    "金額": st.column_config.TextColumn("金額"),
                    "所得類別": st.column_config.SelectboxColumn(
                        "所得類別",
                        options=income_type_options,
                        help="銀行 CSV 不會自動猜所得類別，請 Diana 逐筆補上。",
                    ),
                    "扣繳綜所稅": st.column_config.TextColumn("扣繳綜所稅"),
                    "扣繳二代健保": st.column_config.TextColumn("扣繳二代健保"),
                    "對方": st.column_config.TextColumn("對方"),
                    "說明": st.column_config.TextColumn("說明", width="large"),
                    "備註": st.column_config.TextColumn("備註", width="medium"),
                    "來源": st.column_config.TextColumn("來源", disabled=True),
                    "來源列": st.column_config.TextColumn("來源列", disabled=True),
                    "信心": st.column_config.NumberColumn("信心", format="%.2f", disabled=True),
                },
            )

            if st.button("Diana 勾選確認後寫入", type="primary", key=f"bank_csv_commit_{selected_bank}"):
                imported = 0
                skipped = 0
                errors = []

                for idx, row in edited_bank_df.iterrows():
                    if not bool(row.get("匯入", False)):
                        skipped += 1
                        continue

                    income_type = str(row.get("所得類別", "") or "").strip()
                    if income_type not in R.INCOME_TYPE_LABELS_ZH:
                        skipped += 1
                        errors.append(f"第 {idx+1} 筆：請先選所得類別")
                        continue

                    try:
                        row_date = pd.to_datetime(row["日期"]).date()
                        raw_description = str(row.get("說明", "") or "").strip()
                        notes = str(row.get("備註", "") or "").strip()
                        combined_notes = raw_description if not notes else f"{raw_description}\n{notes}" if raw_description else notes

                        income = Income(
                            date=row_date,
                            amount=Decimal(str(row["金額"])),
                            income_type=income_type,
                            tax_withheld=Decimal(str(row.get("扣繳綜所稅", 0) or 0)),
                            nhi_withheld=Decimal(str(row.get("扣繳二代健保", 0) or 0)),
                            status="received",
                            received_date=row_date,
                            notes=combined_notes,
                            tax_year=R.TAX_YEAR,
                            source=str(row.get("來源", "bank_csv") or "bank_csv"),
                        )
                        save_income(income)
                        imported += 1
                    except Exception as e:
                        skipped += 1
                        errors.append(f"第 {idx+1} 筆：{e}")

                st.success(f"✅ 銀行 CSV 匯入 {imported} 筆，跳過 {skipped} 筆")
                if errors:
                    st.error("錯誤：\n" + "\n".join(errors[:10]))
        elif uploaded_bank_csv:
            st.info("這份銀行 CSV 沒有解析出可匯入的入帳列。")

    st.markdown("---")

    st.subheader("手動整理後 CSV 匯入")

    st.markdown("""
    **CSV 欄位要求**（可 Excel 做好再上傳）：
    - 必填：`日期` (YYYY-MM-DD), `金額`, `所得類別` (50/9A/9B_author/9B_speech/9B_other/92)
    - 選填：`案主`, `扣繳綜所稅`, `扣繳二代健保`, `狀態`, `入帳日`, `備註`
    """)

    # 範例 template
    template_df = pd.DataFrame([
        {
            '日期': '2025-04-15',
            '金額': 30000,
            '所得類別': '9B_speech',
            '案主': '某大學',
            '扣繳綜所稅': 3000,
            '扣繳二代健保': 633,
            '狀態': 'received',
            '入帳日': '2025-04-20',
            '備註': '專題演講鐘點費',
        },
        {
            '日期': '2025-03-10',
            '金額': 50000,
            '所得類別': '9B_author',
            '案主': '某出版社',
            '扣繳綜所稅': 5000,
            '扣繳二代健保': 1055,
            '狀態': 'received',
            '入帳日': '2025-03-15',
            '備註': '稿費',
        },
    ])
    template_csv = template_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📄 下載 CSV 範本", data=template_csv, file_name="diana_tax_template.csv", mime="text/csv")

    st.markdown("---")

    uploaded = st.file_uploader("上傳 CSV", type=['csv'])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            st.write("**預覽（前 10 筆）**")
            st.dataframe(df.head(10), use_container_width=True)
            st.caption(f"共 {len(df)} 筆")

            if st.button("✅ 確認匯入", type="primary"):
                imported = 0
                skipped = 0
                errors = []

                # 準備現有案主 map
                existing_clients = {c.name: c.id for c in list_clients()}

                for idx, row in df.iterrows():
                    try:
                        # 案主：如果填了但不存在，新建
                        client_id = None
                        client_name = row.get('案主', '')
                        if pd.notna(client_name) and str(client_name).strip():
                            client_name = str(client_name).strip()
                            if client_name in existing_clients:
                                client_id = existing_clients[client_name]
                            else:
                                new_c = save_client(Client(name=client_name))
                                existing_clients[client_name] = new_c.id
                                client_id = new_c.id

                        inc = Income(
                            date=pd.to_datetime(row['日期']).date(),
                            amount=Decimal(str(row['金額'])),
                            income_type=str(row['所得類別']).strip(),
                            tax_withheld=Decimal(str(row.get('扣繳綜所稅', 0) or 0)),
                            nhi_withheld=Decimal(str(row.get('扣繳二代健保', 0) or 0)),
                            client_id=client_id,
                            status=str(row.get('狀態', 'invoiced') or 'invoiced'),
                            received_date=pd.to_datetime(row['入帳日']).date() if pd.notna(row.get('入帳日')) else None,
                            notes=str(row.get('備註', '') or ''),
                            tax_year=R.TAX_YEAR,
                            source='csv_import',
                        )
                        save_income(inc)
                        imported += 1
                    except Exception as e:
                        errors.append(f"第 {idx+2} 列：{e}")
                        skipped += 1

                st.success(f"✅ 匯入 {imported} 筆，跳過 {skipped} 筆")
                if errors:
                    st.error("錯誤：\n" + "\n".join(errors[:10]))

        except Exception as e:
            st.error(f"讀不了這個 CSV：{e}")


# ============================================================
# Tab 2: JSON 備份 / 還原
# ============================================================
with tab2:
    st.subheader("完整備份")
    st.caption("把所有資料備份成 JSON，可以放雲端 / 匯給你的會計")

    if st.button("💾 產生備份 JSON"):
        incomes = list_incomes(tax_year=R.TAX_YEAR, limit=10000)
        clients = list_clients()

        backup = {
            'generated_at': date.today().isoformat(),
            'tax_year': R.TAX_YEAR,
            'clients': [
                {'id': str(c.id), 'name': c.name, 'tax_id': c.tax_id, 'notes': c.notes}
                for c in clients
            ],
            'incomes': [
                {
                    'id': str(inc.id),
                    'date': inc.date.isoformat(),
                    'client_id': str(inc.client_id) if inc.client_id else None,
                    'amount': str(inc.amount),
                    'income_type': inc.income_type,
                    'tax_withheld': str(inc.tax_withheld),
                    'nhi_withheld': str(inc.nhi_withheld),
                    'status': inc.status,
                    'received_date': inc.received_date.isoformat() if inc.received_date else None,
                    'notes': inc.notes,
                }
                for inc in incomes
            ],
        }

        json_str = json.dumps(backup, ensure_ascii=False, indent=2)
        st.download_button(
            "⬇️ 下載 JSON",
            data=json_str.encode('utf-8'),
            file_name=f"diana_backup_{R.TAX_YEAR}.json",
            mime="application/json",
        )


# ============================================================
# Tab 3: 匯出報稅草稿
# ============================================================
with tab3:
    st.subheader("匯出 5 月報稅用草稿")
    st.caption("彙整所有收入、扣繳、試算稅額，產出一份她可以對著財政部官方軟體填的 summary")

    from core.tax_engine import calculate_annual_tax
    from storage.db import get_settings

    incomes = list_incomes(tax_year=R.TAX_YEAR, limit=10000)
    settings = get_settings()
    clients = {c.id: c.name for c in list_clients()}

    if not incomes:
        st.info("還沒收入紀錄")
    else:
        income_dicts = [{'amount': inc.amount, 'income_type': inc.income_type} for inc in incomes]
        result = calculate_annual_tax(
            incomes=income_dicts,
            is_married=settings.is_married,
            dependents=settings.dependents,
            has_elderly_dependent=settings.has_elderly_dependent,
            occupation=settings.occupation,
        )
        total_withheld = sum((inc.tax_withheld for inc in incomes), Decimal(0))
        result.total_tax_withheld = total_withheld

        # 組 markdown 報表
        from io import StringIO
        buf = StringIO()
        buf.write(f"# {R.TAX_YEAR} 年度綜所稅報稅草稿\n\n")
        buf.write(f"產生日期：{date.today()}\n\n")
        buf.write(f"## 個人資料\n\n")
        buf.write(f"- 婚姻：{'已婚' if settings.is_married else '單身'}\n")
        buf.write(f"- 扶養親屬：{settings.dependents} 位\n")
        buf.write(f"- 職業：{R.OCCUPATION_LABELS_ZH.get(settings.occupation, settings.occupation)}\n\n")

        buf.write(f"## 收入彙總\n\n")
        buf.write(f"| 類別 | 金額 |\n|---|---|\n")
        buf.write(f"| 薪資所得 (50) | NT$ {int(result.income_50_total):,} |\n")
        buf.write(f"| 執業 9A | NT$ {int(result.income_9a_total):,} |\n")
        buf.write(f"| 稿費/版稅 9B | NT$ {int(result.income_9b_author_total):,} |\n")
        buf.write(f"| 講演鐘點費 9B | NT$ {int(result.income_9b_speech_total):,} |\n")
        buf.write(f"| 其他 9B | NT$ {int(result.income_9b_other_total):,} |\n")
        buf.write(f"| 其他所得 92 | NT$ {int(result.income_92_total):,} |\n\n")

        buf.write(f"## 稅額試算\n\n")
        buf.write(f"- 綜合所得總額：NT$ {int(result.gross_income):,}\n")
        buf.write(f"- 免稅額：NT$ {int(result.exemption):,}\n")
        buf.write(f"- 標準扣除額：NT$ {int(result.standard_deduction):,}\n")
        buf.write(f"- 薪資特別扣除：NT$ {int(result.salary_special_deduction):,}\n")
        buf.write(f"- 應稅所得淨額：NT$ {int(result.taxable_income):,}\n")
        buf.write(f"- 適用稅率：{result.tax_rate*100:.0f}%\n")
        buf.write(f"- 應納稅額：NT$ {int(result.tax_payable):,}\n")
        buf.write(f"- 已扣繳綜所稅：NT$ {int(result.total_tax_withheld):,}\n\n")

        if result.tax_payable > result.total_tax_withheld:
            buf.write(f"**預估應補繳：NT$ {int(result.tax_payable - result.total_tax_withheld):,}**\n\n")
        else:
            buf.write(f"**預估可退稅：NT$ {int(result.total_tax_withheld - result.tax_payable):,}**\n\n")

        buf.write(f"## 明細（業主彙總）\n\n")
        by_client = {}
        for inc in incomes:
            key = clients.get(inc.client_id, '（不指定）')
            by_client.setdefault(key, []).append(inc)

        for cname, incs in by_client.items():
            total = sum((i.amount for i in incs), Decimal(0))
            tw = sum((i.tax_withheld for i in incs), Decimal(0))
            buf.write(f"### {cname}\n")
            buf.write(f"合計：NT$ {int(total):,}，已扣繳：NT$ {int(tw):,}\n\n")
            buf.write(f"| 日期 | 金額 | 類別 | 扣繳 |\n|---|---|---|---|\n")
            for inc in incs:
                buf.write(f"| {inc.date} | NT$ {int(inc.amount):,} | {R.INCOME_TYPE_LABELS_ZH.get(inc.income_type, '')} | NT$ {int(inc.tax_withheld):,} |\n")
            buf.write("\n")

        buf.write("---\n\n")
        buf.write("⚠️ 本草稿僅為試算參考，實際申報請以財政部電子申報系統為準。\n")

        md = buf.getvalue()
        st.markdown("### 預覽")
        with st.container(border=True):
            st.markdown(md)

        st.download_button(
            "⬇️ 下載 Markdown",
            data=md.encode('utf-8'),
            file_name=f"diana_tax_draft_{R.TAX_YEAR}.md",
            mime="text/markdown",
        )


# ============================================================
# Tab 4: 未來整合
# ============================================================
with tab4:
    st.subheader("🔮 未來會加的整合")
    st.markdown("""
    **v1（1-2 個月）**
    - 📄 **扣繳憑單 PDF OCR**：業主寄電子檔來，丟上去自動抽金額、類型、扣繳額
    - 🏦 **銀行 CSV parser**：台銀 / 玉山 / 國泰 / Richart 各自 parser
    - 📧 **Gmail email 解析**：看到匯款通知自動建 draft 收入
    - 🧾 **電子發票 API**：抓載具費用明細

    **v2（3-6 個月）**
    - 🏛️ **MyData 平台整合**：5 月直接拉所得清單 PDF
    - 🤖 **n8n workflow templates**：你可以組自己的自動化流程
    - 💬 **LINE Bot**：Diana 轉發業主通知給 bot → 自動入庫

    **Blocked**
    - 直接送申報到財政部（無 API 且違法）
    - 代開發票（需稅籍登記）
    """)
