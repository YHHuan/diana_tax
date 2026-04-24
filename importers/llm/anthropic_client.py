"""
Anthropic Claude API wrapper — keep all LLM calls isolated here so the rest
of the codebase stays pure Python with no SDK coupling.

Usage:
    client = AnthropicClient()            # reads ANTHROPIC_API_KEY
    result = client.extract_with_tool(
        system="You extract tax slip fields.",
        user_text="Parse this PDF into the schema.",
        tool_schema=SLIP_TOOL_SCHEMA,
        document_bytes=pdf_bytes,
        document_media_type="application/pdf",
    )
    # result is the dict matching tool_schema["input_schema"]
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Optional


class AnthropicNotConfigured(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is missing or the SDK isn't installed."""


@dataclass
class ExtractResult:
    data: dict[str, Any]
    raw_text: str
    model: str
    input_tokens: int
    output_tokens: int


class AnthropicClient:
    # Haiku 4.5 is cheap and fast; PDF understanding is solid on modest layouts.
    # Upgrade per-call to sonnet-4-6 if a slip has unusual formatting.
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise AnthropicNotConfigured(
                "ANTHROPIC_API_KEY not set. Export the key or pass api_key=."
            )
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise AnthropicNotConfigured(
                "anthropic SDK not installed. Add 'anthropic' to requirements.txt."
            ) from e

        self._sdk = anthropic
        self._client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL

    def extract_with_tool(
        self,
        system: str,
        user_text: str,
        tool_schema: dict,
        document_bytes: Optional[bytes] = None,
        document_media_type: str = "application/pdf",
        model: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> ExtractResult:
        """
        Run a tool-forced extraction. Returns the dict the model produced
        as tool input, raising if the model refused to call the tool.
        """
        content: list[dict] = []
        if document_bytes is not None:
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": document_media_type,
                    "data": base64.standard_b64encode(document_bytes).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": user_text})

        resp = self._client.messages.create(
            model=model or self.model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
            messages=[{"role": "user", "content": content}],
        )

        tool_blocks = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_blocks:
            text = "\n".join(
                getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
            )
            raise RuntimeError(f"Model did not invoke the extraction tool. Text response: {text!r}")

        tool = tool_blocks[0]
        raw_text = "\n".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        return ExtractResult(
            data=dict(tool.input),
            raw_text=raw_text,
            model=resp.model,
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
        )
