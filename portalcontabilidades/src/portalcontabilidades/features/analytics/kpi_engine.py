"""Financial KPIs: PMR, PMP, Financial Cycle, Break-even, and Liquidity ratios."""
from decimal import Decimal
from typing import Dict, Any


def calculate_financial_kpis(
    avg_receivables: Decimal,
    total_sales: Decimal,
    avg_payables: Decimal,
    total_purchases: Decimal,
    fixed_expenses: Decimal,
    contribution_margin_pct: Decimal,
    current_assets: Decimal,
    current_liabilities: Decimal,
    net_income: Decimal
) -> Dict[str, Any]:
    """Computes executive financial ratios according to Brazilian accounting standards (NBC TG / CPC 26)."""
    # 1. Prazo Médio de Recebimento (PMR = (Receber Médio / Vendas) * 360)
    pmr_days = float(((avg_receivables / total_sales) * Decimal("360")).quantize(Decimal("0.1"))) if total_sales > 0 else 0.0

    # 2. Prazo Médio de Pagamento (PMP = (Pagar Médio / Compras) * 360)
    pmp_days = float(((avg_payables / total_purchases) * Decimal("360")).quantize(Decimal("0.1"))) if total_purchases > 0 else 0.0

    # 3. Ciclo Financeiro (PMR - PMP)
    financial_cycle_days = pmr_days - pmp_days

    # 4. Ponto de Equilíbrio (Break-even Point = Custos Fixos / Margem Contribuição)
    margin_ratio = contribution_margin_pct / Decimal("100")
    break_even_point = float((fixed_expenses / margin_ratio).quantize(Decimal("0.01"))) if margin_ratio > 0 else 0.0

    # 5. Índice de Liquidez Corrente (Ativo Circulante / Passivo Circulante)
    liquidity_ratio = float((current_assets / current_liabilities).quantize(Decimal("0.01"))) if current_liabilities > 0 else 0.0

    # 6. Lucratividade Líquida (% sobre Vendas)
    net_profitability_pct = float(((net_income / total_sales) * Decimal("100")).quantize(Decimal("0.01"))) if total_sales > 0 else 0.0

    return {
        "prazo_medio_recebimento_dias": pmr_days,
        "prazo_medio_pagamento_dias": pmp_days,
        "ciclo_financeiro_dias": financial_cycle_days,
        "ponto_de_equilibrio_reais": break_even_point,
        "indice_liquidez_corrente": liquidity_ratio,
        "lucratividade_liquida_pct": net_profitability_pct
    }
