"""
資料模型 — SQLModel (pydantic + SQLAlchemy)

設計原則：
1. 所有欄位有 sensible default，Diana 可以只填最必要的
2. 所有金額用 Decimal，避免 float 誤差
3. ID 用 UUID，未來多人架構不用改
4. 時間全部 UTC 存，顯示時轉 Asia/Taipei
"""

import datetime as dt
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import SQLModel, Field, Relationship


# ============================================================
# Client — 案主
# ============================================================

class Client(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    tax_id: Optional[str] = None          # 統一編號
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Project — 專案 / 合約
# ============================================================

class Project(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id")
    name: str
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None

    # 預期總額（合約價，實際入帳記在 Income）
    expected_total: Optional[Decimal] = None
    currency: str = "TWD"

    # 預設所得類別（這個案子的多筆收入預設用這個類型）
    default_income_type: str = "9B_other"

    contract_file: Optional[str] = None   # 附檔路徑
    notes: str = ""
    archived: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Income — 單筆收入
# ============================================================

class Income(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # 關聯
    client_id: Optional[UUID] = Field(default=None, foreign_key="client.id")
    project_id: Optional[UUID] = Field(default=None, foreign_key="project.id")

    # 基本資訊
    date: dt.date = Field(index=True)          # 發生日（發票日 / 業主給付日）
    amount: Decimal                          # 給付總額
    currency: str = "TWD"

    # 稅務分類
    income_type: str                         # 參考 rules_114.IncomeType
    tax_year: int = 114                      # 所屬稅年度

    # 扣繳資訊
    tax_withheld: Decimal = Decimal(0)       # 已扣綜所稅
    nhi_withheld: Decimal = Decimal(0)       # 已扣二代健保

    # 狀態
    status: str = "invoiced"                 # invoiced / received / overdue / cancelled
    received_date: Optional[dt.date] = None     # 實際入帳日

    # 附件與備註
    proof_files: Optional[str] = None        # JSON list of file paths
    notes: str = ""

    # 來源 tracking
    source: str = "manual"                   # manual / csv_import / email / slip_ocr / mydata

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# WithholdingSlip — 扣繳憑單（以業主為單位）
# ============================================================

class WithholdingSlip(SQLModel, table=True):
    """
    扣繳憑單是業主年底給的彙總文件。
    與 Income 的關係：一張扣繳憑單通常對應多筆 Income（同業主整年）。
    5 月對帳時用這個跟 MyData 資料比對。
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tax_year: int
    payer_name: str
    payer_tax_id: Optional[str] = None
    income_type: str                          # 50 / 9A / 9B
    gross_amount: Decimal                     # 給付總額
    tax_withheld: Decimal
    nhi_withheld: Decimal = Decimal(0)
    slip_file: Optional[str] = None           # 原始 PDF 路徑
    source: str = "manual"                    # manual / pdf_ocr / mydata
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Expense — 費用（v1 之後會用到）
# ============================================================

class Expense(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    date: dt.date
    amount: Decimal
    currency: str = "TWD"
    category: str = "other"                   # 交通 / 設備 / 通訊 / 辦公 / 其他
    project_id: Optional[UUID] = Field(default=None, foreign_key="project.id")
    description: str = ""
    receipt_file: Optional[str] = None
    tax_deductible: bool = True
    source: str = "manual"                    # manual / einvoice_api / receipt_ocr
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Settings — 個人設定（single row）
# ============================================================

class UserSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)

    # 個人身分
    name: str = ""
    is_married: bool = False
    dependents: int = 0                       # 扶養親屬數
    has_elderly_dependent: bool = False       # 是否撫養 70+ 親屬

    # 職業（影響 9B 費用率）
    occupation: str = "default"               # 對應 rules_114.EXPENSE_RATES

    # 費用率模式
    expense_mode: str = "standard"            # standard (用財政部費用率) / itemized (列舉實際)

    # 健保狀態（影響二代健保扣繳）
    nhi_insurance_type: str = "union"         # union (工會) / employer (正職) / other
    has_regular_job: bool = False             # 有其他正職 → 很多業主會幫他扣，但不扣二代健保

    # 扣除額選擇
    deduction_mode: str = "standard"          # standard / itemized

    updated_at: datetime = Field(default_factory=datetime.utcnow)
