"""
扣繳憑單 PDF 解析 — Claude API based.

典型業主給 Diana 的扣繳憑單長這樣（格式 9A / 9B / 50 三種）：
- 扣繳單位：XX 有限公司（統編 12345678）
- 納稅義務人：黃雅涵（身分證 A22...）
- 所得類別：執行業務所得 9B / 薪資 50 / ...
- 給付總額：100,000
- 扣繳稅額：10,000
- 補充保險費：2,110
- 所得年度：114

我們要把這些欄位萃取成 SlipDraft。用 Claude 的 tool_use 強制結構化輸出，
不走 regex — 因為業主給的格式千奇百怪（PDF、圖檔掃描、word 導出）。
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional, Union

from .common import SlipDraft
from .llm.anthropic_client import AnthropicClient, ExtractResult


# tool_use schema — Claude 會填這個 schema 的欄位
SLIP_TOOL_SCHEMA = {
    "name": "record_withholding_slip",
    "description": (
        "記錄一張台灣綜所稅扣繳憑單的結構化資料。只有當你在文件中直接看到對應欄位才填；"
        "看不到或有疑慮的欄位留空字串（字串欄位）或 null（數字欄位）。不要猜、不要合併不同張的資料。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tax_year": {
                "type": "integer",
                "description": "所得年度（民國年，例 114）。若文件用西元年請換算：西元 − 1911。",
            },
            "payer_name": {
                "type": "string",
                "description": "扣繳單位名稱（業主 / 公司 / 機構名）。",
            },
            "payer_tax_id": {
                "type": ["string", "null"],
                "description": "扣繳單位統一編號（8 位數字），看不到填 null。",
            },
            "income_type": {
                "type": "string",
                "enum": ["50", "9A", "9B_author", "9B_speech", "9B_other", "92"],
                "description": (
                    "所得類別代號。判斷規則：\n"
                    "- 50 = 薪資所得、兼職薪資、授課鐘點費（訓練班/公司員工訓練/研習系列）\n"
                    "- 9A = 執行業務所得（律師/會計師/設計師/表演等）\n"
                    "- 9B_author = 稿費、版稅、樂譜、作曲、編劇、漫畫\n"
                    "- 9B_speech = 一次性對外演講、學術演講\n"
                    "- 9B_other = 其他 9B 執業所得（經紀、補習班授課費等）\n"
                    "- 92 = 其他所得（競賽獎金、偶發性所得等）\n"
                    "若文件只寫「所得類別 9B」沒有進一步區分，預設 9B_other。"
                ),
            },
            "gross_amount": {
                "type": "number",
                "description": "給付總額（新台幣元，整數）。PDF 常寫成 $100,000 或 100,000 元，去掉符號和逗號。",
            },
            "tax_withheld": {
                "type": "number",
                "description": "已扣繳綜所稅（元，整數）。無扣繳填 0。",
            },
            "nhi_withheld": {
                "type": "number",
                "description": "已扣繳二代健保補充保費（元，整數）。沒有這欄位填 0。",
            },
            "confidence": {
                "type": "number",
                "description": (
                    "0.0–1.0 自評信心度：看得很清楚所有欄位 → 0.9+；"
                    "有欄位用猜的 / 格式怪 → 0.5–0.7；"
                    "極模糊或缺欄 → < 0.5。"
                ),
            },
            "notes": {
                "type": "string",
                "description": "任何你判讀時的不確定、特殊情況、或建議 Diana 手動確認的地方。",
            },
        },
        "required": [
            "tax_year",
            "payer_name",
            "income_type",
            "gross_amount",
            "tax_withheld",
            "nhi_withheld",
            "confidence",
            "notes",
        ],
    },
}


SLIP_SYSTEM_PROMPT = """\
你是台灣稅務資料判讀助手。使用者會上傳一張「各類所得扣繳暨免扣繳憑單」PDF 或其他格式文件，\
你必須呼叫 record_withholding_slip 工具把關鍵欄位填進結構化 schema。

重要原則：
1. 只填你在文件上直接看得到的欄位。推論出來的要在 notes 註記。
2. 民國 / 西元年要判準：若寫 2025 年請換算成 114。
3. 金額去掉 $ 與逗號，統一以新台幣整數填入。
4. 所得類別（income_type）務必對應到 enum 之一；不確定的記在 notes 裡。
5. 若一張 PDF 含多張扣繳憑單，只處理第一張，並在 notes 寫「此檔含多張憑單，請分拆上傳」。
6. 絕對不要編造 payer_tax_id。看不到就填 null。
"""


def _validate_and_build(data: dict, raw_text: str) -> SlipDraft:
    # Fill optional defaults if model omitted them
    tax_year = int(data["tax_year"])
    if tax_year > 1911:
        # Claude sometimes keeps AD format if unsure
        tax_year = tax_year - 1911

    return SlipDraft(
        tax_year=tax_year,
        payer_name=str(data["payer_name"]).strip(),
        payer_tax_id=(data.get("payer_tax_id") or None),
        income_type=str(data["income_type"]),
        gross_amount=Decimal(str(data["gross_amount"])),
        tax_withheld=Decimal(str(data["tax_withheld"])),
        nhi_withheld=Decimal(str(data.get("nhi_withheld", 0))),
        source="slip_ocr",
        confidence=float(data.get("confidence", 0.5)),
        raw_text=raw_text,
        notes=str(data.get("notes", "")),
    )


def parse_slip(
    source: Union[Path, bytes],
    client: Optional[AnthropicClient] = None,
    media_type: str = "application/pdf",
) -> SlipDraft:
    """
    Parse a 扣繳憑單 from PDF bytes or a file path.

    Pass an existing AnthropicClient to batch many slips; otherwise one is
    created on the fly (reads ANTHROPIC_API_KEY).
    """
    if isinstance(source, (str, Path)):
        pdf_bytes = Path(source).read_bytes()
    else:
        pdf_bytes = source

    if client is None:
        client = AnthropicClient()

    result: ExtractResult = client.extract_with_tool(
        system=SLIP_SYSTEM_PROMPT,
        user_text="請讀這張扣繳憑單並呼叫 record_withholding_slip 工具把欄位填進去。",
        tool_schema=SLIP_TOOL_SCHEMA,
        document_bytes=pdf_bytes,
        document_media_type=media_type,
    )

    return _validate_and_build(result.data, raw_text=result.raw_text)
