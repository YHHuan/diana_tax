"""
Slip OCR tests — LLM call is mocked. We're verifying:
- tool schema shape is what we expect (so Claude knows what to return)
- _validate_and_build correctly converts AD year → ROC year
- SlipDraft population maps model output → dataclass
- AnthropicClient raises AnthropicNotConfigured on missing key

Not tested here: actual Claude PDF extraction quality. That's a manual
acceptance test run separately with real PDFs under Diana's direction.
"""

import sys
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from importers.common import SlipDraft
from importers.slip_ocr import (
    SLIP_TOOL_SCHEMA,
    _validate_and_build,
    parse_slip,
)


class TestToolSchema:

    def test_required_fields_present(self):
        req = set(SLIP_TOOL_SCHEMA["input_schema"]["required"])
        assert req >= {
            "tax_year",
            "payer_name",
            "income_type",
            "gross_amount",
            "tax_withheld",
            "nhi_withheld",
        }

    def test_income_type_enum_is_rules_114_aligned(self):
        props = SLIP_TOOL_SCHEMA["input_schema"]["properties"]
        enum = set(props["income_type"]["enum"])
        assert enum == {"50", "9A", "9B_author", "9B_speech", "9B_other", "92"}

    def test_payer_tax_id_allows_null(self):
        props = SLIP_TOOL_SCHEMA["input_schema"]["properties"]
        assert "null" in props["payer_tax_id"]["type"]


class TestValidateAndBuild:

    def _model_output(self, **overrides):
        out = {
            "tax_year": 114,
            "payer_name": "ABC 有限公司",
            "payer_tax_id": "12345678",
            "income_type": "9B_speech",
            "gross_amount": 30_000,
            "tax_withheld": 3_000,
            "nhi_withheld": 633,
            "confidence": 0.9,
            "notes": "",
        }
        out.update(overrides)
        return out

    def test_basic_build(self):
        d = _validate_and_build(self._model_output(), raw_text="")
        assert isinstance(d, SlipDraft)
        assert d.tax_year == 114
        assert d.payer_name == "ABC 有限公司"
        assert d.payer_tax_id == "12345678"
        assert d.income_type == "9B_speech"
        assert d.gross_amount == Decimal(30_000)
        assert d.tax_withheld == Decimal(3_000)
        assert d.nhi_withheld == Decimal(633)
        assert d.confidence == 0.9
        assert d.source == "slip_ocr"

    def test_ad_year_converted_to_roc(self):
        """模型若誤填西元 2025，自動換算成民國 114"""
        d = _validate_and_build(self._model_output(tax_year=2025), raw_text="")
        assert d.tax_year == 114

    def test_tax_id_null_kept_as_none(self):
        d = _validate_and_build(self._model_output(payer_tax_id=None), raw_text="")
        assert d.payer_tax_id is None

    def test_tax_id_empty_string_kept_as_none(self):
        d = _validate_and_build(self._model_output(payer_tax_id=""), raw_text="")
        assert d.payer_tax_id is None

    def test_amounts_converted_to_decimal(self):
        d = _validate_and_build(
            self._model_output(gross_amount="100000.00", tax_withheld="10000", nhi_withheld="2110"),
            raw_text="raw",
        )
        assert d.gross_amount == Decimal("100000.00")
        assert d.tax_withheld == Decimal("10000")
        assert d.nhi_withheld == Decimal("2110")

    def test_notes_preserved(self):
        d = _validate_and_build(self._model_output(notes="多張合併，需 Diana 確認"), raw_text="")
        assert "多張" in d.notes


class TestParseSlipWithMockedClient:

    def test_happy_path(self):
        class FakeResult:
            def __init__(self):
                self.data = {
                    "tax_year": 114,
                    "payer_name": "國立台灣大學",
                    "payer_tax_id": "03734901",
                    "income_type": "9B_speech",
                    "gross_amount": 5000,
                    "tax_withheld": 0,  # < 20,000 免扣
                    "nhi_withheld": 0,
                    "confidence": 0.95,
                    "notes": "",
                }
                self.raw_text = ""
                self.model = "test-model"
                self.input_tokens = 100
                self.output_tokens = 50

        class FakeClient:
            def extract_with_tool(self, **kwargs):
                # sanity: confirm right tool is passed
                assert kwargs["tool_schema"]["name"] == "record_withholding_slip"
                assert kwargs["document_bytes"] == b"%PDF-1.4 fake"
                return FakeResult()

        d = parse_slip(b"%PDF-1.4 fake", client=FakeClient())
        assert d.payer_name == "國立台灣大學"
        assert d.gross_amount == Decimal(5000)
        assert d.tax_withheld == Decimal(0)
        assert d.confidence == 0.95

    def test_from_file_path(self, tmp_path):
        fake_pdf = tmp_path / "slip.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 not a real pdf")

        captured = {}

        class FakeResult:
            data = {
                "tax_year": 2026,  # AD
                "payer_name": "Diana 出版社",
                "payer_tax_id": None,
                "income_type": "9B_author",
                "gross_amount": 250000,
                "tax_withheld": 25000,
                "nhi_withheld": 5275,
                "confidence": 0.8,
                "notes": "payer 統編看不到",
            }
            raw_text = ""
            model = "x"
            input_tokens = 0
            output_tokens = 0

        class FakeClient:
            def extract_with_tool(self, **kwargs):
                captured.update(kwargs)
                return FakeResult()

        d = parse_slip(fake_pdf, client=FakeClient())
        assert captured["document_media_type"] == "application/pdf"
        assert captured["document_bytes"] == b"%PDF-1.4 not a real pdf"
        assert d.tax_year == 115  # 2026 → 115
        assert d.payer_tax_id is None
        assert d.gross_amount == Decimal(250_000)


class TestAnthropicNotConfigured:

    def test_missing_key_raises(self, monkeypatch):
        from importers.llm.anthropic_client import AnthropicClient, AnthropicNotConfigured
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(AnthropicNotConfigured):
            AnthropicClient()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
