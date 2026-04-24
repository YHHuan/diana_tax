"""
統一 importer 接口 — 所有資料來源（bank CSV / slip PDF / email / 電子發票）
都回傳 list[IncomeDraft]。UI 拿到後給 Diana 逐筆預覽、編輯、確認，
Diana 按「存入」才會轉成 core.models.Income 寫進 DB。

為什麼 draft 不是 Income：
- parser 可能猜錯（9B vs 50）、金額格式可能有誤、幣別匯率未處理
- Diana 要能看原始文字、改分類後再存
- 多來源可以 dedup（同一筆入帳同時被 bank CSV 和 email 偵測到）
"""

from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class IncomeDraft:
    date: date
    amount: Decimal
    currency: str = "TWD"

    raw_description: str = ""
    counterparty_hint: Optional[str] = None

    suggested_income_type: Optional[str] = None
    suggested_tax_withheld: Optional[Decimal] = None
    suggested_nhi_withheld: Optional[Decimal] = None

    source: str = "unknown"
    source_row_id: Optional[str] = None
    confidence: float = 0.5

    notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["amount"] = str(self.amount)
        if self.suggested_tax_withheld is not None:
            d["suggested_tax_withheld"] = str(self.suggested_tax_withheld)
        if self.suggested_nhi_withheld is not None:
            d["suggested_nhi_withheld"] = str(self.suggested_nhi_withheld)
        return d


@dataclass
class SlipDraft:
    """
    扣繳憑單 PDF 解析結果。對應 core.models.WithholdingSlip。
    與 IncomeDraft 分開：扣繳憑單是年度彙總文件，Income 是單筆入帳。
    """
    tax_year: int
    payer_name: str
    payer_tax_id: Optional[str]
    income_type: str
    gross_amount: Decimal
    tax_withheld: Decimal
    nhi_withheld: Decimal = Decimal(0)

    source: str = "slip_ocr"
    confidence: float = 0.5
    raw_text: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gross_amount"] = str(self.gross_amount)
        d["tax_withheld"] = str(self.tax_withheld)
        d["nhi_withheld"] = str(self.nhi_withheld)
        return d
