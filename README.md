# Diana Tax 💰

給 Diana 用的台灣自由工作者記帳 × 報稅助手。

**這是 v0 骨架** — 稅算引擎完整、UI 可用、SQLite 儲存。先跑起來 Diana 開始填資料，下一階段再加匯入器、LLM 解析。

---

## 快速啟動

### Mac
```bash
cd diana-tax
chmod +x start.command
./start.command
```
或在 Finder 雙擊 `start.command`

### Windows
雙擊 `start.bat`

### Linux / WSL
```bash
cd diana-tax
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run ui/app.py
```

啟動後會自動打開 http://localhost:8501

---

## 功能（v0）

- **📊 Dashboard** — 本年度收入總覽、預估稅額、預估退補
- **➕ 新增收入** — 一筆一筆記（3 個必填），智能提示業主應扣多少
- **📋 收入明細** — Excel-like 表格、可篩選排序、CSV 匯出
- **🧮 稅額試算** — 現況 / 假設情境 / 類別比較
- **👤 個人設定** — 婚姻、扶養、職業、健保
- **📤 匯入/匯出** — CSV 匯入、JSON 備份、報稅草稿 Markdown

---

## 資料夾結構

```
diana-tax/
├── PLAN.md               ← 完整計畫書（看這個理解路線圖）
├── README.md             ← 就這個
├── requirements.txt
├── start.command / .bat  ← 一鍵啟動
│
├── core/                 ← 稅算核心（pure Python）
│   ├── rules_114.py      ← 114 年度稅法參數
│   ├── tax_engine.py     ← 計算邏輯
│   └── models.py         ← 資料模型
│
├── storage/
│   └── db.py             ← SQLite + SQLModel
│
├── ui/
│   ├── app.py            ← Streamlit 主頁
│   └── pages/            ← 子頁面
│
├── tests/
│   └── test_tax_engine.py ← 20 個 case
│
└── data/                 ← SQLite DB 在這（.gitignore）
```

---

## 測試

```bash
python -m pytest tests/ -v
```

應該看到 `20 passed`。

---

## 下一步 roadmap

- **v1（1–2 月）**：銀行 CSV 匯入、扣繳憑單 PDF OCR、email 解析
- **v2（3–6 月）**：MyData 整合、Railway 部署
- 完整路線圖看 `PLAN.md`

---

## ⚠️ 重要免責

本工具僅為試算參考，**不構成稅務諮詢**。實際申報請以財政部官方系統為準。
稅額計算涵蓋 114 年度參數，資料來源：財政部賦稅署 2024/11/28 公告。
