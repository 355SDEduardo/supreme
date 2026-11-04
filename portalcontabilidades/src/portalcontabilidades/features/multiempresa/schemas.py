"""Pydantic schemas for Feature 09: Gestão Multiempresa."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CompanyCreate(BaseModel):
    organization_id: str
    corporate_name: str = Field(..., min_length=2, max_length=255)
    trade_name: Optional[str] = None
    tax_id: str = Field(..., description="CNPJ or CPF")
    tax_regime: str = Field("simples_nacional", description="simples_nacional, lucro_presumido, lucro_real, mei, imune_isenta")
    state_tax_id: Optional[str] = None
    municipal_tax_id: Optional[str] = None
    cnae_code: Optional[str] = None
    parent_company_id: Optional[str] = None


class CompanyResponse(BaseModel):
    id: str
    organization_id: str
    corporate_name: str
    trade_name: Optional[str]
    tax_id: str
    tax_regime: str
    state_tax_id: Optional[str]
    municipal_tax_id: Optional[str]
    cnae_code: Optional[str]
    status: str
    parent_company_id: Optional[str]
    created_at: datetime


class CockpitSummaryResponse(BaseModel):
    total_companies: int
    active_companies: int
    companies_in_good_standing: int
    companies_with_pending_documents: int
    average_closing_progress_pct: float
    by_tax_regime: Dict[str, int]
    cnd_alerts_count: int
    unreconciled_transactions_total: int


class BatchRequestDocumentsInput(BaseModel):
    organization_id: str
    target_tax_regime: Optional[str] = None  # e.g. 'simples_nacional'
    company_ids: Optional[List[str]] = None
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})
    checklist_template: str = "padrao_mensal"


class BatchOperationResult(BaseModel):
    total_requested: int
    success_count: int
    failed_count: int
    errors: List[Dict[str, str]]
    completed_at: datetime


class AnalystAssignmentInput(BaseModel):
    analyst_user_id: str
    department: str = "geral"


class SwitchContextInput(BaseModel):
    target_company_id: str


class SwitchContextResponse(BaseModel):
    active_company_id: str
    corporate_name: str
    tax_id: str
    role: str
    new_token: str
