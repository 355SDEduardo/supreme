"""DRE (Demonstração do Resultado do Exercício) Accrual Calculation Engine."""
from decimal import Decimal
from typing import Dict, Any, List, Optional


def calculate_dre_structure(
    gross_revenue: Decimal,
    sales_deductions: Decimal,
    cogs: Decimal,
    operating_expenses: Decimal,
    financial_revenues: Decimal,
    financial_expenses: Decimal,
    prior_period_dre: Optional[Dict[str, Decimal]] = None
) -> Dict[str, Any]:
    """Computes legal multilevel DRE statement with Vertical and Horizontal Analysis."""
    net_revenue = gross_revenue - sales_deductions
    gross_profit = net_revenue - cogs
    ebitda = gross_profit - operating_expenses
    financial_result = financial_revenues - financial_expenses
    net_income = ebitda + financial_result

    # Safe Vertical Analysis (% of Gross Revenue)
    def calc_va(amount: Decimal) -> float:
        if gross_revenue == Decimal("0.00"):
            return 0.0
        return float(((amount / gross_revenue) * Decimal("100")).quantize(Decimal("0.01")))

    # Safe Horizontal Analysis (% of change vs prior period)
    def calc_ha(current_amt: Decimal, prior_amt: Optional[Decimal]) -> Optional[float]:
        if not prior_amt or prior_amt == Decimal("0.00"):
            return None
        return float((((current_amt - prior_amt) / abs(prior_amt)) * Decimal("100")).quantize(Decimal("0.01")))

    prior = prior_period_dre or {}

    lines = [
        {
            "code": "1",
            "description": "Receita Bruta de Vendas e Serviços",
            "amount": float(gross_revenue),
            "vertical_analysis_pct": calc_va(gross_revenue),
            "horizontal_analysis_pct": calc_ha(gross_revenue, prior.get("gross_revenue")),
            "is_total": False
        },
        {
            "code": "2",
            "description": "(-) Deduções e Impostos sobre Vendas",
            "amount": float(-abs(sales_deductions)),
            "vertical_analysis_pct": calc_va(-abs(sales_deductions)),
            "horizontal_analysis_pct": calc_ha(sales_deductions, prior.get("sales_deductions")),
            "is_total": False
        },
        {
            "code": "3",
            "description": "(=) Receita Líquida",
            "amount": float(net_revenue),
            "vertical_analysis_pct": calc_va(net_revenue),
            "horizontal_analysis_pct": calc_ha(net_revenue, prior.get("net_revenue")),
            "is_total": True
        },
        {
            "code": "4",
            "description": "(-) Custos dos Produtos / Serviços Vendidos (CPV/CSV)",
            "amount": float(-abs(cogs)),
            "vertical_analysis_pct": calc_va(-abs(cogs)),
            "horizontal_analysis_pct": calc_ha(cogs, prior.get("cogs")),
            "is_total": False
        },
        {
            "code": "5",
            "description": "(=) Lucro Bruto",
            "amount": float(gross_profit),
            "vertical_analysis_pct": calc_va(gross_profit),
            "horizontal_analysis_pct": calc_ha(gross_profit, prior.get("gross_profit")),
            "is_total": True
        },
        {
            "code": "6",
            "description": "(-) Despesas Operacionais (Administrativas, Pessoal, Comerciais)",
            "amount": float(-abs(operating_expenses)),
            "vertical_analysis_pct": calc_va(-abs(operating_expenses)),
            "horizontal_analysis_pct": calc_ha(operating_expenses, prior.get("operating_expenses")),
            "is_total": False
        },
        {
            "code": "7",
            "description": "(=) EBITDA / LAJIDA",
            "amount": float(ebitda),
            "vertical_analysis_pct": calc_va(ebitda),
            "horizontal_analysis_pct": calc_ha(ebitda, prior.get("ebitda")),
            "is_total": True
        },
        {
            "code": "8",
            "description": "(+/-) Resultado Financeiro Líquido",
            "amount": float(financial_result),
            "vertical_analysis_pct": calc_va(financial_result),
            "horizontal_analysis_pct": calc_ha(financial_result, prior.get("financial_result")),
            "is_total": False
        },
        {
            "code": "9",
            "description": "(=) Lucro Líquido do Exercício",
            "amount": float(net_income),
            "vertical_analysis_pct": calc_va(net_income),
            "horizontal_analysis_pct": calc_ha(net_income, prior.get("net_income")),
            "is_total": True
        }
    ]

    return {
        "gross_revenue": float(gross_revenue),
        "net_revenue": float(net_revenue),
        "gross_profit": float(gross_profit),
        "ebitda": float(ebitda),
        "net_income": float(net_income),
        "gross_margin_pct": calc_va(gross_profit),
        "ebitda_margin_pct": calc_va(ebitda),
        "net_margin_pct": calc_va(net_income),
        "lines": lines
    }
