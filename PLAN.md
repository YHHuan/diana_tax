# Diana Tax — 台灣自由工作者記帳 × 報稅助手

**Single-user 專案**：給 Diana 用，先不商品化。但架構 future-proof，未來要擴到多人/商品化時不用重寫。

---

## 0. Vision / What we're building

一個**多功能 Excel-like 的工具**，讓 Diana 在一個地方：

1. **記錄**每筆接案收入（日期、案主、金額、類型、附檔）
2. **整合**她各種收入入口（多銀行、業主通知 email、電子發票、平台匯款）
3. **分類**到台灣所得稅格式代號（9A / 9B / 50 / 92 / 海外）
4. **試算**年度應繳 / 退補稅額，含二代健保補充保費
5. **提醒**應收未收款、合約到期、報稅截止日
6. **產出**一份「報稅日草稿 PDF / Excel」，她 5 月對著財政部官方軟體填

**不做**：
- 代客報稅（法律紅線）
- 自動送出申報（技術上無 API 且違法）
- 保管她的自然人憑證 / 健保卡密碼
- 任何銀行資金移動

---

## 1. 用戶與場景（Diana 的實際 user journey）

### 持續性場景（每月 / 每季）
- **收到匯款 → 記一筆**：LINE / email 通知進帳 → 快速 log 一筆，貼截圖
- **簽新合約 → 建專案**：新客戶、金額、週期、扣繳方式
- **收到扣繳憑單 PDF → 丟進系統**：LLM 解析出金額、類型、已扣繳
- **月底對帳**：Wise / 台灣銀行 CSV 下載 → 匯入 → 比對有沒有缺筆
- **追款**：某案主 overdue → 系統提醒 → 自動產生催款文字草稿

### 一次性場景（一年一次）
- **1 月**：去年度所有收入快速 review、錯漏補登
- **5 月**：MyData 下載綜所資料清單 → 與系統對帳 → 產報稅草稿 → 到官方軟體填

### 探索性場景
- **「如果我再接一個 10 萬的案子，要繳多少稅？」**：試算器
- **「這個業主給我的是薪資還是 9B？差多少？」**：情境比較
- **「現在年度累積收入多少？扣到多少稅了？年底會不會補稅？」**：Dashboard

---

## 2. 資料模型（核心 entities）

```
Client（案主）
├─ name, contact, tax_id, notes
└─ 一對多 Project

Project（專案 / 合約）
├─ client, name, start_date, end_date, contract_type
├─ expected_total, currency, default_income_type
├─ 附檔：合約 PDF
└─ 一對多 Income

Income（單筆收入 / 給付）
├─ date, project, client, amount, currency
├─ income_type: 50 / 9A / 9B_author / 9B_speech / 9B_other / 92 / overseas
├─ tax_withheld（已扣繳綜所稅 10%）
├─ nhi_withheld（已扣繳二代健保 2.11%）
├─ status: invoiced / received / overdue
├─ received_date
├─ proofs: 匯款水單、扣繳憑單、email 截圖
└─ notes

Expense（費用 / 成本）  -- 可選，for 列舉費用率
├─ date, category, amount, project（選填）
├─ receipt_image / e_invoice_data
└─ tax_deductible: bool

WithholdingSlip（扣繳憑單）
├─ tax_year, payer, payer_tax_id
├─ income_type, gross_amount, tax_withheld, nhi_withheld
└─ source: manual / pdf_ocr / mydata

Settings（個人設定）
├─ profile: 單身/已婚/撫養人數
├─ occupation_type: 著作人 / 講師 / 設計師 / ...
├─ expense_rate_mode: 標準費用率 / 列舉實際
├─ labor_insurance: 工會加保 / 無 / 其他
└─ tax_year_context: 114 / 115
```

---

## 3. 功能路線圖

### v0（這週 ship）— 本地可用的基礎骨架
- [x] 核心稅算引擎（114 年度參數寫死，單元測試覆蓋）
- [x] 資料模型 + SQLite 儲存
- [x] Streamlit UI：新增收入 / 收入列表 / Dashboard / 試算器
- [x] 匯出 CSV / JSON
- [x] 本地啟動腳本（Windows .bat / Mac .command）

### v1（1-2 個月）— 資料流自動化
- [ ] 銀行 CSV 匯入器（台銀、玉山、國泰世華、Richart、Wise 各自一個 parser）
- [ ] 電子發票 API 整合（費用端自動拉）
- [ ] 扣繳憑單 PDF 上傳 + LLM 結構化（Claude API）
- [ ] Email 通知解析（gmail → 新收入 draft）
- [ ] 應收未收提醒 + 催款訊息產生器
- [ ] 匯出「報稅草稿 PDF」

### v2（3-6 個月）— 深度整合
- [ ] MyData 整合（若數位部核准）
- [ ] 自然人憑證 / TW FidO 登入（選擇性）
- [ ] n8n workflow template：email → parse → insert
- [ ] 多年度資料對比
- [ ] 部署到 Railway / Fly.io（Diana 不用在你 local 跑）

### v3+（視情況）
- [ ] 多用戶（真要商品化時）
- [ ] Open Banking TSP（要過資安驗證）
- [ ] 記帳士 marketplace

---

## 4. 技術架構

### Stack 選擇理由
| 層 | 選 | 為什麼 |
|---|---|---|
| Language | Python 3.11+ | 你熟、生態豐富、LLM lib 完整 |
| UI | Streamlit | 非 coder 可用、10 分鐘起步、Python native |
| DB | SQLite → Postgres(v2+) | v0 零配置，v2 上 Railway 再換 |
| ORM | SQLModel | pydantic 相容、typed、schema migration 好處理 |
| LLM | Anthropic Claude API | 扣繳憑單解析、email 分類 |
| Tests | pytest | |
| File storage | local `data/` → S3/Supabase Storage(v2) | |
| Deploy | local → Railway (v2) | |

### 架構分層
```
┌─────────────────────────────────────┐
│  ui/ — Streamlit pages              │
│   app.py / pages/*.py               │
├─────────────────────────────────────┤
│  core/ — pure Python, no I/O        │
│   tax_engine.py (計算)              │
│   models.py (dataclasses)           │
│   rules/ (每年稅法參數)             │
├─────────────────────────────────────┤
│  importers/ — 各種資料來源          │
│   bank_csv/*.py                     │
│   einvoice_api.py                   │
│   slip_ocr.py (Claude API)          │
│   email_gmail.py                    │
├─────────────────────────────────────┤
│  storage/ — DB layer                │
│   db.py (SQLModel engine)           │
│   migrations/                       │
├─────────────────────────────────────┤
│  tests/ — pytest                    │
└─────────────────────────────────────┘
```

**核心設計原則：core 層是 pure function，沒 I/O**。這樣 tax_engine 可以任何時候抽出來寫 CLI、做 API、丟 Lambda。

---

## 5. 資料來源矩陣（收入入口 × 整合方式）

| 來源 | Diana 的觸發點 | v0 方式 | v1 方式 | v2 方式 |
|---|---|---|---|---|
| 台灣銀行匯款 | 簡訊 / 網銀 | 手動新增 | CSV 匯入 | Open Banking |
| 玉山銀行 | Richart app | 手動新增 | CSV 匯入 | Open Banking |
| 國泰世華 | MyB2B | 手動新增 | CSV 匯入 | Open Banking |
| 業主 email 通知 | Gmail | 手動新增 | Gmail API + LLM | n8n workflow |
| 業主 LINE 通知 | LINE | 手動新增 | LINE screenshot + LLM | LINE Bot |
| 業主開的扣繳憑單 | email PDF | 手動填欄位 | PDF OCR + LLM | MyData 直拉 |
| 平台分潤（YouTube/Medium） | 平台 dashboard | 手動月結 | 平台 API 直連 | — |
| 稿費 / 版稅（出版社） | email + 匯款 | 手動 | PDF OCR | — |
| 課程平台（Hahow/Udemy） | 平台月結 | 手動 | 平台 API / 爬 dashboard | — |
| 海外匯款（Wise） | Wise app | 手動（scope 外） | Wise API | — |
| 電子發票（費用端） | 載具 | — | 電子發票 API | — |
| MyData 扣繳清單 | 財政部 | — | 手動下載匯入 | 直接 OAuth 拉 |

---

## 6. 台灣稅法參數（114 年度，2026/5 申報用）

### 6.1 綜所稅
- 免稅額：97,000 / 人（滿 70 歲 145,500）
- 標準扣除額：131,000（單）/ 262,000（有配偶）
- 薪資所得特別扣除額：218,000
- 基本生活費：213,000 / 人
- 課稅級距（114 年度速算公式）：
  - 590,000 以下 × 5%
  - 590,001–1,330,000 × 12% − 41,300
  - 1,330,001–2,660,000 × 20% − 147,700
  - 2,660,001–4,980,000 × 30% − 413,700
  - 4,980,001+ × 40% − 911,700

### 6.2 執行業務所得費用率（113 年度標準，114 年沿用中）
- 律師：30%
- 會計師 / 建築師：35%
- 地政士：30%
- **著作人（稿費、版稅、樂譜、作曲、編劇、漫畫、講演鐘點費）：30%**
- **著作人自行出版：75%**
- 保險經紀人：26%
- 一般經紀人：20%
- 表演人：45%
- 節目製作人：45%
- 書畫家 / 版畫家：30%
- 工匠 / 美術工藝家：30%

### 6.3 稿費 18 萬免稅額
稿費、版稅、樂譜、作曲、編劇、漫畫、**講演鐘點費**
- 年合計 ≤ 180,000 → 全額免稅
- 超過 180,000 部分 → 減 30% 費用後為執業所得

### 6.4 9B vs 50 判定（講師費最常踩）
- **授課鐘點費 = 50 薪資**：訓練班、講習會、研討會、研習營等系列課程
- **講演鐘點費 = 9B**：一次性專題演講、學術演講
- 公司員工訓練：幾乎都是 50
- 對外公開演講：傾向 9B

### 6.5 二代健保補充保費（2026 年現制）
- 費率 2.11%
- 單次 9A/9B 給付 ≥ 20,000 → 扣
- 單次兼職薪資（50）≥ 28,590（基本工資）→ 扣
- 已加保於職業工會者可檢證豁免
- **注意**：2027 可能改「年累計制」（衛福部 2025/11 預告，暫緩中）

### 6.6 其他
- 勞退自提：6% 以內不計入執業收入課稅
- 海外所得：670 萬基本免稅額（最低稅負制）

---

## 7. UX 設計原則

1. **像 Excel 一樣的主表格**：收入 entries 是中心，能直接編輯、排序、filter
2. **一步新增**：「本月新收入」→ 一個 modal，3 個必填（日期、金額、案主），其他可後補
3. **聰明預設**：記住上次填的類型、案主、費用率
4. **Always-on Dashboard**：不管在哪頁都能看到年度累積、預估稅、待收款
5. **LLM 助手入口**：貼一段 email / 匯款截圖 → 「這是什麼？」→ 自動判斷類型、填欄位
6. **中文優先 UI**：但術語保留（9A/9B/50），hover 顯示白話解釋
7. **低 cognitive load**：不用記稅法，系統用邏輯推，用戶看到「建議填 9B（講演鐘點費）」+ 為什麼

---

## 8. 隱私與資安（single-user 階段的簡化版）

- **全部 local-first**：SQLite + `data/` 資料夾在她電腦上
- **不傳雲**：除了 LLM API call（只傳單筆資料，不傳整個 DB）
- **LLM 隱私**：給 Claude API 的內容她自己決定要傳什麼；預設 opt-in 而非預設
- **不存 credential**：銀行網銀密碼、自然人憑證 PIN 一律不存
- **備份**：`data/backups/` 自動每日 snapshot（SQLite 複製），她可以丟雲端
- **未來商品化時**：必須過 ISO 27001、TLS、row-level security、auth 重寫

---

## 9. 法律邊界（重要）

**可以做**：
- 純軟體算稅給她參考（類 TurboTax）
- 分類建議（「建議填 9B」+ 理由）
- 匯出 PDF / Excel 給她自己填官方軟體
- 解析她下載的資料（扣繳憑單 PDF）

**絕對不做**：
- 以她名義送出綜所稅申報（第三方 API 不存在 + 違法）
- 自稱「會計師」「記帳士」
- 收費提供稅務代理服務（觸碰記帳士法 §35）

**灰色區，未來商品化要 legal review**：
- 收費提供「試算服務」vs「稅務諮詢」界線
- 幫用戶保管 MyData access token
- 自動產生催款法律文件

---

## 10. 測試策略

1. **Tax engine unit tests**：
   - 知名案例比對財政部「114 年度綜合所得稅試算表」
   - 邊界條件：590k / 1.33M / 2.66M / 4.98M 級距切換
   - 9B 稿費 18 萬免稅額
   - 二代健保起扣點 20,000
2. **Regression tests**：每年參數更新時跑一輪
3. **End-to-end test with Diana**：她真的把 2025 的資料倒進來看對不對

---

## 11. 部署與運維

### v0 / v1（Diana 在你 local 或她 local）
- 你跑：`streamlit run ui/app.py`，Diana 透過 Tailscale / ngrok / localhost 連
- 她跑：雙擊 `start.command` (Mac) / `start.bat` (Win) 啟動

### v2+（要讓 Diana 不依賴你）
- Railway 部署（你熟，paper_lobster 已在上面）
- Supabase Postgres + Auth
- Cloudflare Tunnel

---

## 12. Open Questions / 待 Diana 確認

1. **職業類別**：她主要做什麼？影響 9B 費用率預設
   - 著作人 30% / 講師 30% / 表演 45% / 其他？
2. **扣繳憑單格式**：業主都給電子 PDF？紙本？混合？
3. **業主類型**：公司法人為多？個人業主？
4. **發票需求**：有要自行開發票給業主嗎？（這會影響要不要整合發票平台）
5. **目標 UI**：Streamlit 網頁 OK 嗎？還是偏好 Notion-like？
6. **LLM 使用意願**：把扣繳憑單 PDF 傳到 Claude API 解析，OK 嗎？
7. **婚姻 / 扶養狀況**：影響免稅額計算
8. **勞保 / 健保**：工會加保？有正職？影響二代健保扣繳豁免

---

## 13. 已知風險 / 待解問題

- **稅法參數更新**：每年 11 月財政部公告，要定期手動更新 `core/rules/`
- **匯率處理**：海外收入 v2 再處理，涉及申報日匯率 vs 收款日匯率
- **Streamlit 限制**：多用戶時 session 管理弱，要換 FastAPI + React（v2+）
- **LLM 幻覺**：扣繳憑單 OCR 必須給用戶確認、不能自動入庫
- **Gmail / banking 被 2FA / CAPTCHA 擋**：所以我們走「用戶手動下載 CSV 上傳」而非爬蟲，更穩
