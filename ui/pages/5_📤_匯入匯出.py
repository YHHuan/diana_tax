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

from storage.db import DATA_DIR, list_incomes, save_income, list_clients, save_client, get_session
from core.models import Income, Client
from core import rules_114 as R
from importers.bank_csv import parse as parse_bank_csv
from importers.common import IncomeDraft
from importers.dedup import find_batch_duplicates, find_existing_duplicates
from importers.email_gmail import (
    DEFAULT_GMAIL_QUERY,
    GmailNotConfigured,
    fetch_income_drafts_from_gmail,
    save_uploaded_gmail_credentials,
)
from core.fx import parse_fx_rate, convert_drafts_to_twd


st.set_page_config(page_title="匯入 / 匯出", page_icon="📤", layout="wide")
st.title("📤 匯入 / 匯出")

tab1, tab2, tab3, tab4 = st.tabs(["📥 CSV 匯入", "📦 JSON 備份/還原", "💾 匯出報稅草稿", "🔮 未來整合"])

GMAIL_DIR = DATA_DIR / "gmail"
GMAIL_CLIENT_SECRET_PATH = GMAIL_DIR / "client_secret.json"
GMAIL_TOKEN_PATH = GMAIL_DIR / "token.json"


def _drafts_from_dicts(items: list[dict]) -> list[IncomeDraft]:
    drafts: list[IncomeDraft] = []
    for item in items:
        drafts.append(
            IncomeDraft(
                date=pd.to_datetime(item["date"]).date(),
                amount=Decimal(str(item["amount"])),
                currency=str(item.get("currency", "TWD") or "TWD"),
                raw_description=str(item.get("raw_description", "") or ""),
                counterparty_hint=item.get("counterparty_hint"),
                suggested_income_type=item.get("suggested_income_type"),
                suggested_tax_withheld=Decimal(str(item["suggested_tax_withheld"]))
                if item.get("suggested_tax_withheld") is not None
                else None,
                suggested_nhi_withheld=Decimal(str(item["suggested_nhi_withheld"]))
                if item.get("suggested_nhi_withheld") is not None
                else None,
                source=str(item.get("source", "unknown") or "unknown"),
                source_row_id=item.get("source_row_id"),
                confidence=float(item.get("confidence", 0.5) or 0.5),
                notes=str(item.get("notes", "") or ""),
                extra=dict(item.get("extra", {}) or {}),
            )
        )
    return drafts


def _build_preview_rows(drafts: list[IncomeDraft]) -> list[dict]:
    existing_incomes = list_incomes(tax_year=R.TAX_YEAR, limit=10000)
    batch_duplicates = find_batch_duplicates(drafts)
    existing_duplicates = find_existing_duplicates(drafts, existing_incomes)

    rows: list[dict] = []
    for index, draft in enumerate(drafts):
        duplicate_reason = existing_duplicates.get(index) or batch_duplicates.get(index) or ""
        original_amount = draft.extra.get("original_amount", str(draft.amount))
        original_currency = draft.extra.get("original_currency", draft.currency)
        rows.append(
            {
                "匯入": not bool(duplicate_reason),
                "日期": draft.date.isoformat(),
                "金額(TWD)": str(draft.amount),
                "原始金額": str(original_amount),
                "原始幣別": str(original_currency),
                "所得類別": draft.suggested_income_type or "",
                "扣繳綜所稅": "0",
                "扣繳二代健保": "0",
                "對方": draft.counterparty_hint or "",
                "說明": draft.raw_description,
                "備註": draft.notes,
                "來源": draft.source,
                "來源列": draft.source_row_id or "",
                "信心": draft.confidence,
                "重複警告": duplicate_reason,
            }
        )
    return rows


def _render_import_editor(rows: list[dict], *, editor_key: str):
    income_type_options = [""] + list(R.INCOME_TYPE_LABELS_ZH.keys())
    return st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        use_container_width=True,
        key=editor_key,
        column_config={
            "匯入": st.column_config.CheckboxColumn("匯入"),
            "日期": st.column_config.TextColumn("日期"),
            "金額(TWD)": st.column_config.TextColumn("金額(TWD)"),
            "原始金額": st.column_config.TextColumn("原始金額", disabled=True),
            "原始幣別": st.column_config.TextColumn("原始幣別", disabled=True),
            "所得類別": st.column_config.SelectboxColumn("所得類別", options=income_type_options),
            "扣繳綜所稅": st.column_config.TextColumn("扣繳綜所稅"),
            "扣繳二代健保": st.column_config.TextColumn("扣繳二代健保"),
            "對方": st.column_config.TextColumn("對方"),
            "說明": st.column_config.TextColumn("說明", width="large"),
            "備註": st.column_config.TextColumn("備註", width="large"),
            "來源": st.column_config.TextColumn("來源", disabled=True),
            "來源列": st.column_config.TextColumn("來源列", disabled=True),
            "信心": st.column_config.NumberColumn("信心", format="%.2f", disabled=True),
            "重複警告": st.column_config.TextColumn("重複警告", disabled=True, width="medium"),
        },
    )


def _commit_import_rows(edited_df: pd.DataFrame, *, button_key: str, button_label: str):
    if not st.button(button_label, type="primary", key=button_key):
        return

    imported = 0
    skipped = 0
    errors = []

    for idx, row in edited_df.iterrows():
        if not bool(row.get("匯入", False)):
            skipped += 1
            continue

        duplicate_warning = str(row.get("重複警告", "") or "").strip()
        if duplicate_warning.startswith("與既有收入重複"):
            skipped += 1
            errors.append(f"第 {idx+1} 筆：{duplicate_warning}")
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
            counterparty = str(row.get("對方", "") or "").strip()
            extra_notes = [part for part in (counterparty, raw_description) if part]
            summary = " | ".join(extra_notes)
            combined_notes = summary if not notes else f"{summary}\n{notes}" if summary else notes

            income = Income(
                date=row_date,
                amount=Decimal(str(row["金額(TWD)"])),
                currency="TWD",
                income_type=income_type,
                tax_withheld=Decimal(str(row.get("扣繳綜所稅", 0) or 0)),
                nhi_withheld=Decimal(str(row.get("扣繳二代健保", 0) or 0)),
                status="received",
                received_date=row_date,
                notes=combined_notes,
                tax_year=R.TAX_YEAR,
                source=str(row.get("來源", "import") or "import"),
            )
            save_income(income)
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"第 {idx+1} 筆：{e}")

    st.success(f"✅ 匯入 {imported} 筆，跳過 {skipped} 筆")
    if errors:
        st.error("錯誤：\n" + "\n".join(errors[:10]))


def _get_fx_rates_from_inputs(*, key_prefix: str, currencies: set[str]) -> dict[str, Decimal]:
    rates: dict[str, Decimal] = {}
    if not currencies:
        return rates

    st.caption("非 TWD 金額先換算為 TWD 再寫入正式收入。請填 Diana 決定採用的匯率。")
    cols = st.columns(max(1, min(3, len(currencies))))
    for idx, currency in enumerate(sorted(currencies)):
        with cols[idx % len(cols)]:
            rate_value = st.text_input(
                f"{currency} -> TWD",
                value="",
                placeholder="例如 31.80",
                key=f"{key_prefix}_fx_{currency}",
            )
        try:
            rate = parse_fx_rate(rate_value)
        except Exception as exc:
            st.warning(f"{currency} 匯率格式錯誤：{exc}")
            continue
        if rate is not None:
            rates[currency] = rate
    return rates


# ============================================================
# Tab 1: CSV 匯入
# ============================================================
with tab1:
    # === 銀行 CSV ===
    st.subheader("銀行 CSV 匯入")
    st.caption("先把銀行入帳明細解析成草稿，再由 Diana 勾選、補所得類別後寫入正式收入。系統會先做跨來源 dedup 檢查。")

    bank_options = {
        "cathay": "國泰世華 MyB2B / CUBE",
        "esun": "玉山個人網銀 CSV",
        "richart": "Richart app / 匯出明細 CSV",
        "twb": "台灣銀行 e-go 個人網銀 CSV",
        "wise": "Wise statement CSV",
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
            non_twd_currencies = {
                str(draft.currency or "TWD").upper()
                for draft in drafts
                if str(draft.currency or "TWD").upper() != "TWD"
            }
            if selected_bank == "wise" and non_twd_currencies:
                fx_rates = _get_fx_rates_from_inputs(
                    key_prefix=f"wise_{uploaded_bank_csv.name}",
                    currencies=non_twd_currencies,
                )
                drafts, fx_warnings = convert_drafts_to_twd(drafts, fx_rates)
                if fx_warnings:
                    st.warning("未完成換匯的列會被略過：\n" + "\n".join(fx_warnings))

            st.write("**銀行 CSV 草稿預覽**")
            edited_bank_df = _render_import_editor(
                _build_preview_rows(drafts),
                editor_key=f"bank_csv_editor_{selected_bank}_{uploaded_bank_csv.name}",
            )
            _commit_import_rows(
                edited_bank_df,
                button_key=f"bank_csv_commit_{selected_bank}",
                button_label="Diana 勾選確認後寫入",
            )
        elif uploaded_bank_csv:
            st.info("這份銀行 CSV 沒有解析出可匯入的入帳列。")

    st.markdown("---")

    st.subheader("Gmail 匯款通知匯入")
    st.caption("用 Gmail API 抓最近的匯款／付款通知，先轉成草稿再由 Diana 決定是否寫入。")

    uploaded_gmail_secret = st.file_uploader(
        "上傳 Google OAuth client secret JSON",
        type=["json"],
        key="gmail_oauth_json",
        help="請在 Google Cloud Console 建立 Desktop app OAuth client 後下載 JSON。",
    )
    if uploaded_gmail_secret is not None:
        try:
            save_uploaded_gmail_credentials(uploaded_gmail_secret.getvalue(), GMAIL_CLIENT_SECRET_PATH)
            st.success(f"OAuth client 已儲存到 {GMAIL_CLIENT_SECRET_PATH}")
        except Exception as exc:
            st.error(f"OAuth client JSON 儲存失敗：{exc}")

    gmail_query = st.text_input(
        "Gmail 搜尋條件",
        value=DEFAULT_GMAIL_QUERY,
        key="gmail_import_query",
    )
    gmail_max_results = st.number_input(
        "最多抓幾封",
        min_value=1,
        max_value=100,
        value=15,
        step=1,
        key="gmail_import_limit",
    )

    if st.button("📬 抓最近通知", key="gmail_fetch_button"):
        if not GMAIL_CLIENT_SECRET_PATH.exists():
            st.error("先上傳 Google OAuth client secret JSON。")
        else:
            try:
                gmail_drafts = fetch_income_drafts_from_gmail(
                    GMAIL_CLIENT_SECRET_PATH,
                    GMAIL_TOKEN_PATH,
                    query=gmail_query,
                    max_results=int(gmail_max_results),
                )
                st.session_state["gmail_draft_items"] = [draft.to_dict() for draft in gmail_drafts]
            except GmailNotConfigured as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Gmail 匯入失敗：{exc}")

    gmail_draft_items = st.session_state.get("gmail_draft_items", [])
    if gmail_draft_items:
        gmail_drafts = _drafts_from_dicts(gmail_draft_items)
        gmail_currencies = {
            str(draft.currency or "TWD").upper()
            for draft in gmail_drafts
            if str(draft.currency or "TWD").upper() != "TWD"
        }
        if gmail_currencies:
            gmail_fx_rates = _get_fx_rates_from_inputs(
                key_prefix="gmail_import",
                currencies=gmail_currencies,
            )
            gmail_drafts, gmail_fx_warnings = convert_drafts_to_twd(gmail_drafts, gmail_fx_rates)
            if gmail_fx_warnings:
                st.warning("未完成換匯的 Gmail 草稿會被略過：\n" + "\n".join(gmail_fx_warnings))

        st.write("**Gmail 草稿預覽**")
        edited_gmail_df = _render_import_editor(
            _build_preview_rows(gmail_drafts),
            editor_key="gmail_import_editor",
        )
        _commit_import_rows(
            edited_gmail_df,
            button_key="gmail_import_commit",
            button_label="將勾選的 Gmail 草稿寫入",
        )

    st.markdown("---")

    # === 扣繳憑單 ===
    st.subheader("扣繳憑單 PDF 上傳（Claude OCR）")
    st.caption("上傳後交給 Claude API 結構化抽取。Diana 確認後才寫入 DB。")

    uploaded_slip_pdf = st.file_uploader(
        "上傳扣繳憑單 PDF",
        type=["pdf"],
        key="slip_pdf_uploader",
        accept_multiple_files=False,
    )

    if uploaded_slip_pdf and st.button("🤖 用 Claude 解析", key="slip_pdf_parse_live", type="primary"):
        import os as _os
        from importers.slip_ocr import parse_slip
        from importers.llm.anthropic_client import AnthropicNotConfigured
        if not _os.environ.get("ANTHROPIC_API_KEY"):
            st.error(
                "找不到 ANTHROPIC_API_KEY 環境變數。在啟動 streamlit 前先：\n"
                "```bash\nexport ANTHROPIC_API_KEY=sk-ant-...\n```"
            )
        else:
            with st.spinner("Claude 正在讀 PDF..."):
                try:
                    draft = parse_slip(uploaded_slip_pdf.getvalue())
                    st.session_state["slip_draft"] = draft.to_dict()
                except AnthropicNotConfigured as e:
                    st.error(f"Anthropic 未配置：{e}")
                except Exception as e:
                    st.error(f"解析失敗：{e}")

    if st.session_state.get("slip_draft"):
        draft_dict = st.session_state["slip_draft"]
        st.success(f"✅ 解析完成（confidence: {draft_dict.get('confidence', 0):.2f}）")

        with st.form("confirm_slip_form"):
            st.markdown("**請 Diana 確認／修改後再存：**")
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                c_payer = st.text_input("扣繳單位", value=draft_dict["payer_name"])
                c_tax_id = st.text_input("統編", value=draft_dict.get("payer_tax_id") or "")
            with cc2:
                TYPE_ORDER = ["50", "9A", "9B_author", "9B_speech", "9B_other", "92"]
                default_idx = TYPE_ORDER.index(draft_dict["income_type"]) if draft_dict["income_type"] in TYPE_ORDER else 4
                c_type = st.selectbox("所得類別", TYPE_ORDER, index=default_idx)
                c_year = st.number_input("稅年度（民國）", min_value=100, max_value=130, value=int(draft_dict["tax_year"]))
            with cc3:
                c_gross = st.number_input("給付總額", min_value=0.0, value=float(draft_dict["gross_amount"]))
                c_tax = st.number_input("扣繳綜所稅", min_value=0.0, value=float(draft_dict["tax_withheld"]))
                c_nhi = st.number_input("扣繳二代健保", min_value=0.0, value=float(draft_dict.get("nhi_withheld", 0)))

            c_notes = st.text_area("備註", value=draft_dict.get("notes", ""))
            cols = st.columns(2)
            with cols[0]:
                save = st.form_submit_button("💾 存入扣繳憑單", type="primary")
            with cols[1]:
                clear = st.form_submit_button("🗑️ 丟掉重來")

            if clear:
                st.session_state.pop("slip_draft", None)
                st.rerun()

            if save:
                from core.models import WithholdingSlip
                from decimal import Decimal as _D
                slip = WithholdingSlip(
                    tax_year=int(c_year),
                    payer_name=c_payer.strip(),
                    payer_tax_id=(c_tax_id.strip() or None),
                    income_type=c_type,
                    gross_amount=_D(str(c_gross)),
                    tax_withheld=_D(str(c_tax)),
                    nhi_withheld=_D(str(c_nhi)),
                    source="pdf_ocr",
                    notes=c_notes,
                )
                with get_session() as _s:
                    _s.add(slip)
                    _s.commit()
                st.success("扣繳憑單已存入。")
                st.session_state.pop("slip_draft", None)

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

    from storage.db import get_settings
    from sqlmodel import select
    from core.report import build_markdown_report, IncomeRow, SlipRow
    from core.models import WithholdingSlip
    from core.report_pdf import PdfExportUnavailable, render_markdown_pdf

    incomes = list_incomes(tax_year=R.TAX_YEAR, limit=10000)
    settings = get_settings()
    clients = {c.id: c.name for c in list_clients()}

    if not incomes:
        st.info("還沒收入紀錄")
    else:
        with get_session() as session:
            slips = list(
                session.exec(select(WithholdingSlip).where(WithholdingSlip.tax_year == R.TAX_YEAR))
            )

        income_rows = [
            IncomeRow(
                date=inc.date,
                payer_name=clients.get(inc.client_id, "") if inc.client_id else "",
                amount=inc.amount,
                income_type=inc.income_type,
                tax_withheld=inc.tax_withheld,
                nhi_withheld=inc.nhi_withheld,
            )
            for inc in incomes
        ]
        slip_rows = [
            SlipRow(
                payer_name=slip.payer_name,
                payer_tax_id=slip.payer_tax_id,
                income_type=slip.income_type,
                gross_amount=slip.gross_amount,
                tax_withheld=slip.tax_withheld,
                nhi_withheld=slip.nhi_withheld,
            )
            for slip in slips
        ]

        md = build_markdown_report(
            tax_year=R.TAX_YEAR,
            incomes=income_rows,
            slips=slip_rows,
            is_married=settings.is_married,
            dependents=settings.dependents,
            has_elderly_dependent=settings.has_elderly_dependent,
            occupation=settings.occupation,
            user_name=settings.name,
        )
        st.markdown("### 預覽")
        with st.container(border=True):
            st.markdown(md)

        export_col_1, export_col_2 = st.columns(2)
        with export_col_1:
            st.download_button(
                "⬇️ 下載 Markdown",
                data=md.encode('utf-8'),
                file_name=f"diana_tax_draft_{R.TAX_YEAR}.md",
                mime="text/markdown",
            )
        with export_col_2:
            try:
                pdf_bytes = render_markdown_pdf(md, title=f"{R.TAX_YEAR} 年度綜所稅申報草稿")
            except PdfExportUnavailable as exc:
                st.info(str(exc))
            else:
                st.download_button(
                    "⬇️ 下載 PDF",
                    data=pdf_bytes,
                    file_name=f"diana_tax_draft_{R.TAX_YEAR}.pdf",
                    mime="application/pdf",
                )


# ============================================================
# Tab 4: 未來整合
# ============================================================
with tab4:
    st.subheader("🔮 未來會加的整合")
    st.markdown("""
    **下一波優化**
    - 🌏 **Wise 匯率來源自動化**：現在是 Diana 手動決定採用匯率，下一步可接匯率來源
    - 🧠 **跨來源 dedup 規則加強**：現在已做保守 dedup，下一步可加更多模糊比對
    - 📧 **Gmail 匯入模板**：依不同業主建立專用 query / sender allowlist
    - 🧾 **電子發票 API**：抓載具費用明細

    **v2（3-6 個月）**
    - 🏛️ **MyData 平台整合**：5 月直接拉所得清單 PDF
    - 🤖 **n8n workflow templates**：你可以組自己的自動化流程
    - 💬 **LINE Bot**：Diana 轉發業主通知給 bot → 自動入庫

    **Blocked**
    - 直接送申報到財政部（無 API 且違法）
    - 代開發票（需稅籍登記）
    """)
