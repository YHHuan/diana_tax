"""
稅額計算核心引擎 — 114 年度（2026/5 申報用）

設計原則:
- 純函式，沒有 I/O，沒有 DB 依賴
- 所有金額用 Decimal
- 回傳結果用 dict / dataclass，易於 JSON 序列化 / UI 顯示

主要 API:
- calculate_taxable_income_from_9b(...)  計算某類 9B 收入的應稅所得
- calculate_supplementary_nhi(...)       二代健保補充保費
- calculate_annual_tax(...)              全年度總稅額試算
"""

from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Optional

from . import rules_114 as R


# ============================================================
# 單筆收入 → 應稅所得 / 扣繳（不含年度彙總）
# ============================================================

@dataclass
class IncomeClassification:
    """單筆收入的稅務性質分析"""
    income_type: str
    gross_amount: Decimal

    # 以下由系統計算
    expected_tax_withheld: Decimal = Decimal(0)      # 業主應扣綜所稅
    expected_nhi_withheld: Decimal = Decimal(0)      # 業主應扣二代健保
    expense_rate: float = 0.0                        # 適用費用率
    taxable_portion: Decimal = Decimal(0)            # 計入綜所稅的金額（扣費用後）
    notes: list[str] = field(default_factory=list)


def classify_single_income(
    amount: Decimal,
    income_type: str,
    occupation: str = 'default',
    is_part_time: bool = True,
    annual_9b_author_total: Decimal = Decimal(0),  # 年度稿費 / 講演累計（for 18 萬免稅）
) -> IncomeClassification:
    """
    單筆收入的稅務性質分析。用於「每筆記進來時」立刻告訴 Diana 業主會扣多少、
    她 5 月要報多少。
    """
    amount = Decimal(str(amount))
    result = IncomeClassification(
        income_type=income_type,
        gross_amount=amount,
    )

    if income_type == '50':
        # 薪資所得：業主扣繳依查表或 5%
        # 兼職 50 ≥ 28,590 扣二代健保
        if amount >= R.NHI_THRESHOLD_PART_TIME:
            result.expected_nhi_withheld = (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
            result.notes.append(f"薪資 {amount:,} 超過 {R.NHI_THRESHOLD_PART_TIME:,}，業主會扣 2.11% 二代健保")
        result.expense_rate = 0.0  # 薪資用「薪資特別扣除額」統一扣
        result.taxable_portion = amount
        result.notes.append("薪資所得申報用薪資特別扣除額（年度 218,000）")

    elif income_type == '9A':
        # 執業 9A：扣繳 10%
        result.expected_tax_withheld = amount * Decimal('0.10')
        if amount >= R.NHI_THRESHOLD_9A_9B:
            result.expected_nhi_withheld = (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
            result.notes.append(f"單筆 {amount:,} ≥ 20,000，業主會扣 2.11% 二代健保")
        rate = R.EXPENSE_RATES.get(occupation, R.EXPENSE_RATES['default'])
        result.expense_rate = rate
        result.taxable_portion = amount * Decimal(str(1 - rate))
        result.notes.append(f"費用率 {rate*100:.0f}%（{R.OCCUPATION_LABELS_ZH.get(occupation, occupation)}）")

    elif income_type in ('9B_author', '9B_speech'):
        # 稿費 / 版稅 / 講演 —— 受 18 萬免稅額影響
        # 扣繳規則：單筆 ≥ 20,000 才扣 10% 綜所稅 + 2.11% 二代健保
        if amount >= R.WITHHOLDING_THRESHOLD_9B:
            result.expected_tax_withheld = amount * Decimal('0.10')
            result.expected_nhi_withheld = (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
            result.notes.append(f"單筆 ≥ 20,000，業主會扣 10% 綜所稅 + 2.11% 二代健保")
        else:
            result.notes.append(f"單筆 {amount:,} < 20,000，業主無需扣繳")

        # 年度 18 萬免稅額計算 —— 這一筆能享多少免稅
        remaining_exemption = max(Decimal(0), Decimal(R.AUTHOR_TAX_FREE_LIMIT) - annual_9b_author_total)
        if remaining_exemption >= amount:
            # 整筆在免稅額內
            result.taxable_portion = Decimal(0)
            result.notes.append(f"本筆享年度 180,000 免稅額（剩 {remaining_exemption:,}）")
        else:
            # 部分超出
            taxable_gross = amount - remaining_exemption
            rate = R.EXPENSE_RATES[
                'author_self_publish' if occupation == 'author_self_publish' else 'author'
            ]
            result.expense_rate = rate
            result.taxable_portion = taxable_gross * Decimal(str(1 - rate))
            if remaining_exemption > 0:
                result.notes.append(f"超出免稅額 {taxable_gross:,}，減 {rate*100:.0f}% 費用")
            else:
                result.notes.append(f"已用完 18 萬免稅額，全筆減 {rate*100:.0f}% 費用")

    elif income_type == '9B_other':
        # 9B 其他執業：沒有 18 萬免稅，扣繳規則同上
        if amount >= R.WITHHOLDING_THRESHOLD_9B:
            result.expected_tax_withheld = amount * Decimal('0.10')
            result.expected_nhi_withheld = (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
        rate = R.EXPENSE_RATES.get(occupation, R.EXPENSE_RATES['default'])
        result.expense_rate = rate
        result.taxable_portion = amount * Decimal(str(1 - rate))
        result.notes.append(f"費用率 {rate*100:.0f}%")

    elif income_type == '92':
        # 其他所得：扣繳 10%
        result.expected_tax_withheld = amount * Decimal('0.10')
        result.taxable_portion = amount  # 一般沒費用率

    elif income_type == 'overseas':
        # 海外所得：最低稅負制 670 萬免稅
        result.notes.append("海外所得適用最低稅負制，670 萬免稅額")
        result.taxable_portion = amount  # 另計，本引擎 v0 不深入

    # 職業工會加保豁免二代健保（Diana 最可能的 case）
    # 這裡只是 annotation，實際 withholding 行為還是由業主做
    return result


# ============================================================
# 年度綜所稅試算
# ============================================================

@dataclass
class AnnualTaxResult:
    """全年度稅額試算結果"""

    # 收入面
    income_50_total: Decimal = Decimal(0)          # 薪資毛額
    income_9a_total: Decimal = Decimal(0)
    income_9b_author_total: Decimal = Decimal(0)   # 稿費/版稅 毛額
    income_9b_speech_total: Decimal = Decimal(0)   # 講演 毛額
    income_9b_other_total: Decimal = Decimal(0)
    income_92_total: Decimal = Decimal(0)

    # 應稅面（扣除費用率 / 免稅額後）
    salary_taxable: Decimal = Decimal(0)           # 薪資扣薪資特別扣除額後
    execution_taxable: Decimal = Decimal(0)        # 所有 9A + 9B 扣費用率後
    other_taxable: Decimal = Decimal(0)

    # 扣除額
    exemption: Decimal = Decimal(0)
    standard_deduction: Decimal = Decimal(0)
    salary_special_deduction: Decimal = Decimal(0)
    itemized_deduction: Decimal = Decimal(0)       # 用戶選列舉時

    # 最終
    gross_income: Decimal = Decimal(0)             # 綜合所得總額
    taxable_income: Decimal = Decimal(0)           # 綜合所得淨額
    tax_rate: float = 0.0
    progressive_deduction: Decimal = Decimal(0)
    tax_payable: Decimal = Decimal(0)              # 應納稅額

    # 扣繳
    total_tax_withheld: Decimal = Decimal(0)
    total_nhi_withheld: Decimal = Decimal(0)

    # 退/補
    tax_owed_or_refund: Decimal = Decimal(0)       # + 補繳, − 退稅

    # 說明
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Decimal → str for JSON
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d


def calculate_annual_tax(
    incomes: list[dict],  # each: {amount, income_type}
    is_married: bool = False,
    dependents: int = 0,
    has_elderly_dependent: bool = False,
    occupation: str = 'default',
    itemized_deduction: Optional[Decimal] = None,
    other_deductions: Decimal = Decimal(0),   # 其他特別扣除額（儲蓄、教育、幼兒...）
) -> AnnualTaxResult:
    """
    全年度綜所稅試算。

    incomes: list of {amount: Decimal, income_type: str}
    """
    r = AnnualTaxResult()

    # ---- 收入分類彙總 ----
    for inc in incomes:
        amt = Decimal(str(inc['amount']))
        t = inc['income_type']
        if t == '50':
            r.income_50_total += amt
        elif t == '9A':
            r.income_9a_total += amt
        elif t == '9B_author':
            r.income_9b_author_total += amt
        elif t == '9B_speech':
            r.income_9b_speech_total += amt
        elif t == '9B_other':
            r.income_9b_other_total += amt
        elif t == '92':
            r.income_92_total += amt

    # ---- 薪資部分：扣薪資特別扣除額 ----
    # 薪資所得併入綜合所得總額，然後用「薪資所得特別扣除額」減
    # 扣除額是 min(實際薪資, 218,000)
    r.salary_special_deduction = min(r.income_50_total, Decimal(R.SALARY_SPECIAL_DEDUCTION))

    # ---- 9B 稿費/講演：扣 18 萬免稅額 + 30% 費用 ----
    author_and_speech = r.income_9b_author_total + r.income_9b_speech_total
    if author_and_speech <= R.AUTHOR_TAX_FREE_LIMIT:
        nine_b_author_taxable = Decimal(0)
        r.notes.append(f"稿費/講演合計 {author_and_speech:,} ≤ 180,000，全額免稅")
    else:
        over = author_and_speech - Decimal(R.AUTHOR_TAX_FREE_LIMIT)
        expense_rate = R.EXPENSE_RATES[
            'author_self_publish' if occupation == 'author_self_publish' else 'author'
        ]
        nine_b_author_taxable = over * Decimal(str(1 - expense_rate))
        r.notes.append(f"稿費/講演超出 180,000 部分 {over:,}，減 {expense_rate*100:.0f}% 費用 = {nine_b_author_taxable:,}")

    # ---- 9A + 9B_other：費用率 ----
    expense_rate = R.EXPENSE_RATES.get(occupation, R.EXPENSE_RATES['default'])
    nine_a_taxable = r.income_9a_total * Decimal(str(1 - expense_rate))
    nine_b_other_taxable = r.income_9b_other_total * Decimal(str(1 - expense_rate))

    r.execution_taxable = nine_b_author_taxable + nine_a_taxable + nine_b_other_taxable

    # ---- 其他所得 ----
    r.other_taxable = r.income_92_total

    # ---- 綜合所得總額 ----
    r.gross_income = r.income_50_total + r.execution_taxable + r.other_taxable

    # ---- 免稅額 ----
    exemption_count = 1 + (1 if is_married else 0) + dependents
    elderly_bonus = (R.EXEMPTION_ELDERLY - R.EXEMPTION_PER_PERSON) if has_elderly_dependent else 0
    r.exemption = Decimal(R.EXEMPTION_PER_PERSON) * exemption_count + Decimal(elderly_bonus)

    # ---- 扣除額（標準 or 列舉） ----
    if itemized_deduction is not None:
        r.itemized_deduction = itemized_deduction
        general_deduction = itemized_deduction
    else:
        r.standard_deduction = Decimal(
            R.STANDARD_DEDUCTION_MARRIED if is_married else R.STANDARD_DEDUCTION_SINGLE
        )
        general_deduction = r.standard_deduction

    # ---- 綜合所得淨額 ----
    r.taxable_income = max(
        Decimal(0),
        r.gross_income - r.exemption - general_deduction - r.salary_special_deduction - other_deductions
    )

    # ---- 稅額（速算公式）----
    rate, deduct = R.bracket_for_income(float(r.taxable_income))
    r.tax_rate = rate
    r.progressive_deduction = Decimal(deduct)
    r.tax_payable = max(Decimal(0), r.taxable_income * Decimal(str(rate)) - Decimal(deduct))

    # ---- 退/補 ----
    r.tax_owed_or_refund = r.tax_payable - r.total_tax_withheld

    return r


# ============================================================
# 二代健保補充保費（個人自行試算）
# ============================================================

def calculate_supplementary_nhi_single(
    amount: Decimal,
    income_type: str,
) -> Decimal:
    """
    單筆給付的二代健保補充保費。由業主扣繳，這裡只是試算預期金額。
    """
    amount = Decimal(str(amount))
    if income_type in ('9A', '9B_author', '9B_speech', '9B_other'):
        if amount >= R.NHI_THRESHOLD_9A_9B:
            return (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
    elif income_type == '50':
        if amount >= R.NHI_THRESHOLD_PART_TIME:
            return (amount * Decimal(str(R.NHI_SUPPLEMENTARY_RATE))).quantize(Decimal('1'))
    return Decimal(0)
