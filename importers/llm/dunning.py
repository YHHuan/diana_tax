"""
LLM-enhanced 催款文字草稿 — 呼叫 Claude 幫 Diana 寫得更自然、更有她的語氣。

與 core.receivables.draft_dunning_text_simple 的關係：
- local fallback 永遠能用（沒 API key 也能跑）
- LLM 版優先用，給更個人化、更符合 tone
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from .anthropic_client import AnthropicClient


DUNNING_SYSTEM_PROMPT = """\
你是 Diana（台灣自由工作者）的寫作助理。她需要一段向業主追款的中文訊息草稿。

寫作原則：
1. 語氣符合 tone 指定：polite（客氣但清楚）/firm（直接但不失禮）/neutral（事務性）。
2. 繁體中文，不用「親愛的」這種 AI 味。像 Diana 自己寫給熟識業主的語氣。
3. 必含：發生日期、金額、已逾天數、希望對方下一步做什麼。
4. 禁止：威脅、誇大後果、情緒字詞、emoji。
5. 長度：2–5 句話，不要超過 150 字。
6. 末尾不加「此致敬禮」這種公文結構。
"""


def draft_dunning_text_llm(
    payer_name: str,
    amount: Decimal,
    invoice_date: date,
    days_outstanding: int,
    *,
    tone: str = "polite",
    extra_context: Optional[str] = None,
    client: Optional[AnthropicClient] = None,
    model: Optional[str] = None,
) -> str:
    """
    產出 LLM 版本的催款訊息。若 AnthropicClient 不可用，raises。
    呼叫端應 try/except 並退回 core.receivables.draft_dunning_text_simple。
    """
    if client is None:
        client = AnthropicClient()

    user_text_parts = [
        f"請幫我起草一段催款訊息。",
        f"- 業主：{payer_name}",
        f"- 金額：NT$ {int(amount):,}",
        f"- 服務/開票日期：{invoice_date.isoformat()}",
        f"- 已逾 {days_outstanding} 天未收款",
        f"- Tone: {tone}",
    ]
    if extra_context:
        user_text_parts.append(f"\n額外情境：\n{extra_context}")
    user_text_parts.append("\n請直接輸出訊息本體，不要加「以下是草稿：」等前綴。")

    resp = client._client.messages.create(  # noqa: SLF001 — intentional internal access
        model=model or client.model,
        max_tokens=400,
        system=DUNNING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(user_text_parts)}],
    )
    text_blocks = [b for b in resp.content if getattr(b, "type", None) == "text"]
    if not text_blocks:
        raise RuntimeError("LLM returned no text for dunning draft")
    return text_blocks[0].text.strip()
