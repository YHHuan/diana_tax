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
