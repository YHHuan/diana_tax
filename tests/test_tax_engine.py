"""
稅額計算 unit tests

驗證 case 來源：
- 財政部 114 年度綜合所得稅速算公式
- 不同級距邊界條件
- 9B 稿費 18 萬免稅額
- 二代健保起扣點
"""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from decimal import Decimal
import pytest

from core.tax_engine import (
    calculate_annual_tax,
    classify_single_income,
    calculate_supplementary_nhi_single,
)
from core import rules_114 as R


# ============================================================
# 速算公式驗證
# ============================================================

class TestTaxBrackets:
    """根據財政部 114 年度速算公式驗證"""

    def _make_salary_income(self, amount):
        """做一筆純薪資，方便測試純計算"""
        return [{'amount': Decimal(amount), 'income_type': '50'}]

    def test_zero_income(self):
        r = calculate_annual_tax(incomes=[], is_married=False)
        assert r.tax_payable == Decimal(0)

    def test_at_exemption_threshold(self):
        """單身薪資剛好 44.6 萬（免稅門檻 9.7 + 13.1 + 21.8 = 44.6 萬）"""
        r = calculate_annual_tax(
            incomes=self._make_salary_income(446_000),
            is_married=False,
        )
        assert r.tax_payable == Decimal(0)

    def test_just_over_exemption(self):
        """單身薪資 45 萬 → 超出免稅 4k，稅 200"""
        r = calculate_annual_tax(
            incomes=self._make_salary_income(450_000),
            is_married=False,
        )
        assert r.tax_payable == Decimal(200)

    def test_bracket_5_percent(self):
        """
        單身薪資 100 萬
        扣 9.7（免稅） + 13.1（標扣） + 21.8（薪扣） = 44.6
        應稅 100 - 44.6 = 55.4 萬 → 5% 級距
        55.4 * 5% = 27,700
        """
        r = calculate_annual_tax(
            incomes=self._make_salary_income(1_000_000),
            is_married=False,
        )
        # 容許少量誤差 (元)
        assert abs(r.tax_payable - Decimal(27_700)) < 10

    def test_bracket_12_percent(self):
        """
        單身薪資 150 萬
        應稅 = 150 - 44.6 = 105.4 萬 → 12% 級距
        105.4 * 12% - 4.13 = 12.648 - 4.13 = 8.518 萬 = 85,180
        """
        r = calculate_annual_tax(
            incomes=self._make_salary_income(1_500_000),
            is_married=False,
        )
        expected = Decimal(85_180)
        assert abs(r.tax_payable - expected) < 10


# ============================================================
# 9B 稿費 18 萬免稅
# ============================================================

class TestAuthorExemption:

    def test_author_under_180k_fully_exempt(self):
        """稿費 15 萬 → 全額免稅，應稅 0"""
        r = calculate_annual_tax(
            incomes=[{'amount': Decimal(150_000), 'income_type': '9B_author'}],
        )
        assert r.income_9b_author_total == Decimal(150_000)
        assert r.execution_taxable == Decimal(0)
        assert r.tax_payable == Decimal(0)

    def test_author_exactly_180k_exempt(self):
        """稿費 18 萬 → 剛好免稅"""
        r = calculate_annual_tax(
            incomes=[{'amount': Decimal(180_000), 'income_type': '9B_author'}],
        )
        assert r.execution_taxable == Decimal(0)

    def test_author_over_180k_30pct_expense(self):
        """
        稿費 25 萬
        超出部分 = 7 萬
        減 30% 費用 → 應稅 7 * 0.7 = 4.9 萬
        """
        r = calculate_annual_tax(
            incomes=[{'amount': Decimal(250_000), 'income_type': '9B_author'}],
        )
        assert r.execution_taxable == Decimal(49_000)

    def test_author_and_speech_combined_exemption(self):
        """稿費 10 萬 + 講演 10 萬 = 20 萬，共用 18 萬免稅"""
        r = calculate_annual_tax(
            incomes=[
                {'amount': Decimal(100_000), 'income_type': '9B_author'},
                {'amount': Decimal(100_000), 'income_type': '9B_speech'},
            ],
        )
        # 超出 2 萬，減 30% → 1.4 萬應稅
        assert r.execution_taxable == Decimal(14_000)

    def test_self_publish_75pct_expense(self):
        """自行出版 25 萬稿費 → 超出 7 萬 × (1 − 0.75) = 1.75 萬"""
        r = calculate_annual_tax(
            incomes=[{'amount': Decimal(250_000), 'income_type': '9B_author'}],
            occupation='author_self_publish',
        )
        assert r.execution_taxable == Decimal(17_500)


# ============================================================
# 二代健保補充保費
# ============================================================

class TestSupplementaryNHI:

    def test_9b_under_20k_no_nhi(self):
        """9B 單筆 18,000 → 不扣"""
        nhi = calculate_supplementary_nhi_single(Decimal(18_000), '9B_speech')
        assert nhi == Decimal(0)

    def test_9b_at_threshold_nhi_deducted(self):
        """9B 單筆 20,000 → 扣 20000 * 2.11% = 422"""
        nhi = calculate_supplementary_nhi_single(Decimal(20_000), '9B_speech')
        assert nhi == Decimal(422)

    def test_9b_large_amount_nhi(self):
        """9B 單筆 50,000 → 扣 50000 * 2.11% = 1055"""
        nhi = calculate_supplementary_nhi_single(Decimal(50_000), '9B_author')
        assert nhi == Decimal(1055)

    def test_part_time_salary_under_threshold(self):
        """兼職薪資 25,000 < 基本工資 28,590 → 不扣"""
        nhi = calculate_supplementary_nhi_single(Decimal(25_000), '50')
        assert nhi == Decimal(0)

    def test_part_time_salary_over_threshold(self):
        """兼職薪資 30,000 → 扣"""
        nhi = calculate_supplementary_nhi_single(Decimal(30_000), '50')
        expected = Decimal(30_000) * Decimal('0.0211')
        assert nhi == expected.quantize(Decimal('1'))


# ============================================================
# 單筆收入分類
# ============================================================

class TestSingleIncomeClassification:

    def test_9b_speech_withholding(self):
        """單筆 30,000 講演 → 業主扣 10% 綜所稅 + 2.11% 健保"""
        r = classify_single_income(
            amount=Decimal(30_000),
            income_type='9B_speech',
        )
        assert r.expected_tax_withheld == Decimal(3_000)
        assert r.expected_nhi_withheld == Decimal(633)

    def test_9b_speech_below_threshold(self):
        """單筆 15,000 講演 → 不扣繳"""
        r = classify_single_income(
            amount=Decimal(15_000),
            income_type='9B_speech',
        )
        assert r.expected_tax_withheld == Decimal(0)
        assert r.expected_nhi_withheld == Decimal(0)

    def test_9a_always_withhold_10pct(self):
        """9A 執業 → 不管金額都扣 10%"""
        r = classify_single_income(
            amount=Decimal(5_000),
            income_type='9A',
        )
        assert r.expected_tax_withheld == Decimal(500)


# ============================================================
# 混合案例（Diana-like）
# ============================================================

class TestDianaLikeCase:
    """模擬 Diana 類似的接案情境"""

    def test_mixed_income_realistic(self):
        """
        假設情境：
        - 3 筆講演 @ 30,000 = 90,000 (9B_speech)
        - 2 筆稿費 @ 50,000 = 100,000 (9B_author)
        → 9B 合計 190,000，超 10,000
        - 減 30% → 應稅 7,000
        
        應稅所得 = 7,000
        扣 9.7 萬免稅 + 13.1 萬標扣 = 22.8 萬 > 7,000
        → 應納稅額 0
        """
        incomes = [
            {'amount': Decimal(30_000), 'income_type': '9B_speech'},
            {'amount': Decimal(30_000), 'income_type': '9B_speech'},
            {'amount': Decimal(30_000), 'income_type': '9B_speech'},
            {'amount': Decimal(50_000), 'income_type': '9B_author'},
            {'amount': Decimal(50_000), 'income_type': '9B_author'},
        ]
        r = calculate_annual_tax(incomes=incomes, is_married=False)
        assert r.income_9b_speech_total == Decimal(90_000)
        assert r.income_9b_author_total == Decimal(100_000)
        assert r.execution_taxable == Decimal(7_000)
        assert r.tax_payable == Decimal(0)

    def test_high_income_freelancer(self):
        """
        高收入 freelancer：
        - 50 萬 9A 執業（費用率 30% → 應稅 35 萬）
        - 30 萬 9B 稿費（超 18 萬免稅 = 12 萬 × 70% = 8.4 萬應稅）
        → 總執業應稅 = 43.4 萬
        扣 9.7 + 13.1 = 22.8
        → 應稅淨額 = 20.6 萬
        → 5% × 20.6 = 10,300
        """
        incomes = [
            {'amount': Decimal(500_000), 'income_type': '9A'},
            {'amount': Decimal(300_000), 'income_type': '9B_author'},
        ]
        r = calculate_annual_tax(incomes=incomes, is_married=False, occupation='default')
        # 9A: 500k * 70% = 350k
        # 9B: (300-180)k * 70% = 84k
        # 合計 = 434k
        assert r.execution_taxable == Decimal(434_000)
        # 淨額 434 - 97 - 131 = 206
        assert r.taxable_income == Decimal(206_000)
        # 稅 = 206000 * 5% = 10,300
        assert r.tax_payable == Decimal(10_300)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
