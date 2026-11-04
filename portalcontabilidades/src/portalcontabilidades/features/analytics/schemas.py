"""Pydantic schemas for Feature 07: Fluxo de Caixa, DRE e Dashboards."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DreLineResponse(BaseModel):
    code: str
    description: str
    amount: float
    vertical_analysis_pct: float
    horizontal_analysis_pct: Optional[float]
    is_total: bool


class DreResponse(BaseModel):
    company_id: str
    competence: str
    gross_revenue: float
    net_revenue: float
    gross_profit: float
    ebitda: float
    net_income: float
    gross_margin_pct: float
    ebitda_margin_pct: float
    net_margin_pct: float
    lines: List[DreLineResponse]


class CashFlowTimelineItem(BaseModel):
    date: str
    opening_balance: float
    inflows_total: float
    outflows_total: float
    closing_balance: float
    is_negative: bool


class DeficitAlertItem(BaseModel):
    date: str
    deficit_amount: float
    message: str


class CashFlowResponse(BaseModel):
    company_id: str
    initial_balance: float
    final_projected_balance: float
    has_negative_balance_alert: bool
    deficit_alerts: List[DeficitAlertItem]
    timeline: List[CashFlowTimelineItem]


class KpisResponse(BaseModel):
    company_id: str
    competence: str
    prazo_medio_recebimento_dias: float
    prazo_medio_pagamento_dias: float
    ciclo_financeiro_dias: float
    ponto_de_equilibrio_reais: float
    indice_liquidez_corrente: float
    lucratividade_liquida_pct: float


class ExportReportInput(BaseModel):
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})
    format: str = "pdf"  # pdf or xlsx
