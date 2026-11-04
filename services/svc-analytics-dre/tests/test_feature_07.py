"""Unit and Integration Tests for Feature 07: Fluxo de Caixa, DRE e Dashboards."""


import pytest
from datetime import date
from decimal import Decimal

from svc_analytics_dre.dre_engine import calculate_dre_structure
from svc_analytics_dre.cashflow_engine import calculate_daily_cash_flow
from svc_analytics_dre.kpi_engine import calculate_financial_kpis
from svc_analytics_dre.service import get_company_dre, get_company_cash_flow, get_company_kpis


def test_dre_mathematical_integrity_and_analysis():
    """DoD: DRE calculates strictly under accrual basis with Vertical and Horizontal Analysis."""
    gross = Decimal("200000.00")
    deductions = Decimal("20000.00")  # 10%
    cogs = Decimal("80000.00")        # 40%
    opex = Decimal("40000.00")        # 20%
    fin_rev = Decimal("2000.00")
    fin_exp = Decimal("1000.00")

    prior = {
        "gross_revenue": Decimal("180000.00"),
        "net_revenue": Decimal("162000.00"),
        "gross_profit": Decimal("90000.00"),
        "ebitda": Decimal("55000.00"),
        "net_income": Decimal("56000.00")
    }

    dre = calculate_dre_structure(
        gross_revenue=gross,
        sales_deductions=deductions,
        cogs=cogs,
        operating_expenses=opex,
        financial_revenues=fin_rev,
        financial_expenses=fin_exp,
        prior_period_dre=prior
    )

    # 1. Mathematical equations
    assert dre["net_revenue"] == 180000.00
    assert dre["gross_profit"] == 100000.00
    assert dre["ebitda"] == 60000.00
    assert dre["net_income"] == 61000.00

    # 2. Vertical Analysis %
    assert dre["gross_margin_pct"] == 50.0  # 100k / 200k = 50%
    assert dre["ebitda_margin_pct"] == 30.0 # 60k / 200k = 30%
    assert dre["net_margin_pct"] == 30.5    # 61k / 200k = 30.5%


def test_dre_zero_gross_revenue_division_by_zero_handling():
    """Validates that zero gross revenue does not crash vertical analysis."""
    dre = calculate_dre_structure(
        gross_revenue=Decimal("0.00"),
        sales_deductions=Decimal("0.00"),
        cogs=Decimal("0.00"),
        operating_expenses=Decimal("500.00"),
        financial_revenues=Decimal("0.00"),
        financial_expenses=Decimal("0.00")
    )
    assert dre["gross_margin_pct"] == 0.0
    assert dre["net_income"] == -500.00


def test_cash_flow_mathematical_balance_and_negative_alert():
    """DoD: Opening + In - Out == Closing for each day; negative projected balance alerts with exact deficit."""
    initial = Decimal("10000.00")
    days = [
        {"date": date(2026, 10, 1), "inflows_realized": 2000.0, "outflows_realized": 1000.0}, # closing: 11000
        {"date": date(2026, 10, 2), "inflows_projected": 500.0, "outflows_projected": 15000.0}, # closing: 11000 + 500 - 15000 = -3500 (DEFICIT!)
    ]

    cf = calculate_daily_cash_flow(initial, days)

    # Day 1 check: 10000 + 2000 - 1000 = 11000
    assert cf["timeline"][0]["closing_balance"] == 11000.0

    # Day 2 check: 11000 + 500 - 15000 = -3500
    assert cf["timeline"][1]["closing_balance"] == -3500.0
    assert cf["timeline"][1]["is_negative"] is True

    # Alert detection
    assert cf["has_negative_balance_alert"] is True
    assert len(cf["deficit_alerts"]) == 1
    assert cf["deficit_alerts"][0]["deficit_amount"] == 3500.0
    assert "2026-10-02" in cf["deficit_alerts"][0]["date"]


def test_kpi_formulas():
    """Validates formulas for PMR, PMP, Financial Cycle, Break-even, and Liquidity."""
    kpis = calculate_financial_kpis(
        avg_receivables=Decimal("30000.00"),
        total_sales=Decimal("360000.00"),      # PMR = (30k / 360k) * 360 = 30 days
        avg_payables=Decimal("20000.00"),
        total_purchases=Decimal("240000.00"),  # PMP = (20k / 240k) * 360 = 30 days
        fixed_expenses=Decimal("50000.00"),
        contribution_margin_pct=Decimal("50.0"), # Break-even = 50k / 0.50 = 100,000.00
        current_assets=Decimal("150000.00"),
        current_liabilities=Decimal("100000.00"), # Liquidity = 150k / 100k = 1.50
        net_income=Decimal("36000.00")           # Net profitability = 36k / 360k = 10%
    )

    assert kpis["prazo_medio_recebimento_dias"] == 30.0
    assert kpis["prazo_medio_pagamento_dias"] == 30.0
    assert kpis["ciclo_financeiro_dias"] == 0.0
    assert kpis["ponto_de_equilibrio_reais"] == 100000.00
    assert kpis["indice_liquidez_corrente"] == 1.50
    assert kpis["lucratividade_liquida_pct"] == 10.0
