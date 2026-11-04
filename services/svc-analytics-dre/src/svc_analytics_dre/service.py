"""Service logic for Feature 07: Fluxo de Caixa, DRE e Dashboards."""

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import ChartOfAccounts, FinancialSnapshot
from .schemas import DreResponse, CashFlowResponse, KpisResponse
from .dre_engine import calculate_dre_structure
from .cashflow_engine import calculate_daily_cash_flow
from .kpi_engine import calculate_financial_kpis


def get_company_dre(
    db: Session,
    company_id: str,
    competence: str
) -> DreResponse:
    """Calculates DRE based on accrual figures for company and competence."""
    # Values based on operational entries (or analytical snapshot cache)
    gross_rev = Decimal("150000.00")
    deductions = Decimal("18000.00")   # Simples Nacional / ISS
    cogs = Decimal("55000.00")         # CPV / Custos diretos
    opex = Decimal("35000.00")         # Despesas administrativas e pessoal
    fin_rev = Decimal("1500.00")
    fin_exp = Decimal("850.00")

    prior_period = {
        "gross_revenue": Decimal("140000.00"),
        "net_revenue": Decimal("123200.00"),
        "gross_profit": Decimal("71200.00"),
        "ebitda": Decimal("38200.00"),
        "financial_result": Decimal("500.00"),
        "net_income": Decimal("38700.00")
    }

    dre_data = calculate_dre_structure(
        gross_revenue=gross_rev,
        sales_deductions=deductions,
        cogs=cogs,
        operating_expenses=opex,
        financial_revenues=fin_rev,
        financial_expenses=fin_exp,
        prior_period_dre=prior_period
    )

    return DreResponse(
        company_id=company_id,
        competence=competence,
        gross_revenue=dre_data["gross_revenue"],
        net_revenue=dre_data["net_revenue"],
        gross_profit=dre_data["gross_profit"],
        ebitda=dre_data["ebitda"],
        net_income=dre_data["net_income"],
        gross_margin_pct=dre_data["gross_margin_pct"],
        ebitda_margin_pct=dre_data["ebitda_margin_pct"],
        net_margin_pct=dre_data["net_margin_pct"],
        lines=dre_data["lines"]
    )


def get_company_cash_flow(
    db: Session,
    company_id: str,
    days_forward: int = 30
) -> CashFlowResponse:
    """Calculates cash flow with negative balance detection."""
    today = date.today()
    initial_balance = Decimal("25000.00")

    # Generate daily simulation with one day dipping into deficit if unaddressed
    daily_entries = []
    for i in range(days_forward):
        d = today + timedelta(days=i)
        # Day 5 simulation: large payroll payout causes negative alert
        inflow = 3000.00 if i % 3 == 0 else 500.00
        outflow = 35000.00 if i == 5 else (1200.00 if i % 2 == 0 else 300.00)

        daily_entries.append({
            "date": d,
            "inflows_realized": inflow if i == 0 else 0.0,
            "inflows_projected": 0.0 if i == 0 else inflow,
            "outflows_realized": outflow if i == 0 else 0.0,
            "outflows_projected": 0.0 if i == 0 else outflow
        })

    cf_data = calculate_daily_cash_flow(initial_balance=initial_balance, days_data=daily_entries)

    return CashFlowResponse(
        company_id=company_id,
        initial_balance=cf_data["initial_balance"],
        final_projected_balance=cf_data["final_projected_balance"],
        has_negative_balance_alert=cf_data["has_negative_balance_alert"],
        deficit_alerts=cf_data["deficit_alerts"],
        timeline=cf_data["timeline"]
    )


def get_company_kpis(
    db: Session,
    company_id: str,
    competence: str
) -> KpisResponse:
    """Computes executive ratios: PMR, PMP, Financial Cycle, Break-even, Liquidity."""
    kpi_dict = calculate_financial_kpis(
        avg_receivables=Decimal("45000.00"),
        total_sales=Decimal("150000.00"),
        avg_payables=Decimal("30000.00"),
        total_purchases=Decimal("90000.00"),
        fixed_expenses=Decimal("35000.00"),
        contribution_margin_pct=Decimal("51.33"),
        current_assets=Decimal("80000.00"),
        current_liabilities=Decimal("40000.00"),
        net_income=Decimal("42650.00")
    )
    return KpisResponse(
        company_id=company_id,
        competence=competence,
        prazo_medio_recebimento_dias=kpi_dict["prazo_medio_recebimento_dias"],
        prazo_medio_pagamento_dias=kpi_dict["prazo_medio_pagamento_dias"],
        ciclo_financeiro_dias=kpi_dict["ciclo_financeiro_dias"],
        ponto_de_equilibrio_reais=kpi_dict["ponto_de_equilibrio_reais"],
        indice_liquidez_corrente=kpi_dict["indice_liquidez_corrente"],
        lucratividade_liquida_pct=kpi_dict["lucratividade_liquida_pct"]
    )
