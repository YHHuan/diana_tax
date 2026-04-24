# Bank CSV Formats

## Cathay United Bank (國泰世華)

Status: awaiting Diana's real CSV sample. The parser currently targets the common transaction-export shape inferred for MyB2B / CUBE account-detail CSVs and is intentionally tolerant of header variants.

Expected columns for the current scaffold:

- `交易日` or `交易日期`
- `摘要`
- `對方戶名`
- `存入金額`
- `支出金額`
- Optional direction markers such as `收付別`

Current import rules:

- Only inbound credit rows are emitted as `IncomeDraft`.
- Outflow rows are skipped.
- Rows marked like `自己轉帳` / self-transfer are skipped.
- `raw_description` is built from `摘要` plus `對方戶名`.
- `suggested_income_type` stays empty on purpose; Diana must classify it in the UI.

Public references used to frame this note:

- Cathay corporate cash-management / MyB2B overview: https://www.cathaybk.com.tw/cathaybk/corp/myb2b/
- Cathay receivables overview mentioning transaction-detail collection: https://www.cathaybk.com.tw/cathaybk/corp/myb2b/intro/business-payment/receivable/

These pages confirm the MyB2B export/query context, but they do not publish a canonical CSV header list. Once Diana provides a real export sample, this document and the parser aliases should be tightened to the exact layout.

## E.SUN Bank / Richart (玉山 / Richart)

Status: inferred from common personal-netbank exports plus Richart app statement headers.

Accepted columns:

- Date: `交易日期`, `入帳日期`, `日期`, or `Date`
- Amounts: `存入金額` / `支出金額` or signed `金額` / `Amount`
- Description: `摘要`, `備註`, `說明`, `交易內容`, `Description`, `Memo`, `Details`
- Optional counterparty/direction: `對方戶名`, `對方名稱`, `Counterparty`, `Type`, `收付別`

Current import rules:

- Only inbound rows are emitted as `IncomeDraft`.
- Outflows and obvious self-transfers are skipped.
- Richart-style English headers are treated as a variant of the 玉山 parser and tagged with `extra={"variant": "richart"}`.
- Currency is assumed to be TWD for this parser family.

Known quirks:

- Richart exports often mix English headers with signed amounts instead of separate credit/debit columns.
- Until Diana provides real samples, the parser keeps alias detection broad.

## Bank of Taiwan (台灣銀行)

Status: inferred from e-go personal-netbank transaction-detail exports.

Accepted columns:

- Date: `交易日期`, `交易日`, `日期`, `入帳日`
- Amounts: `存入金額` / `支出金額`, with optional fallback to signed `交易金額`
- Description/counterparty: `摘要`, `備註`, `說明`, `交易內容`, `對方戶名`, `對方名稱`, `附言`
- Optional direction markers: `借貸別`, `收付別`, `交易別`

Current import rules:

- ROC dates such as `114/04/22` are supported.
- Only inbound credit rows are emitted.
- Debit rows and self-transfers are skipped.

Known quirks:

- 台銀 CSVs sometimes rely on `借貸別` instead of signed amounts, so the parser checks both columns and text direction.

## Wise

Status: inferred from Wise statement/account-activity CSV exports.

Accepted columns:

- Date: `Date`, `Created on`, `交易日期`
- Amount: signed `Amount` / `Net amount`, or split `Credit` / `Debit`
- Currency: `Currency`, `currency`, `幣別`
- Description/counterparty: `Description`, `Details`, `Counterparty`, `Recipient`, `Payer`
- Optional direction/type: `Type`, `Direction`

Current import rules:

- Keeps the original row currency in `IncomeDraft.currency`; no FX conversion yet.
- Accepts only `TWD`, `USD`, and `JPY` rows for now.
- Skips outflows and unsupported currencies.
- Adds a note on non-TWD rows so Diana knows FX conversion is still pending.

Known quirks:

- Wise exports are often fully English and may include many non-income rows such as card spend, fees, and conversions.
