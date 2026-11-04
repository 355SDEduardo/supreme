"""Pydantic schemas for Feature 01: Central de Obrigações, Tarefas e Prazos."""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TaxObligationResponse(BaseModel):
    id: str
    code: str
    name: str
    sphere: str
    periodicity: str
    due_day_rule: str
    applicable_regimes: Optional[List[str]]
    has_receipt_required_default: bool


class TaskResponse(BaseModel):
    id: str
    company_id: str
    obligation_code: Optional[str]
    competence: str
    title: str
    statutory_due_date: date
    internal_deadline: date
    status: str
    assigned_to: Optional[str]
    reviewed_by: Optional[str]
    has_receipt_required: bool
    receipt_file_id: Optional[str]
    receipt_file_hash: Optional[str]
    risk_level: str  # 'green', 'yellow_alert', 'red_critical', 'overdue'
    days_to_due: int
    created_at: datetime


class TaskStatusUpdate(BaseModel):
    new_status: str
    user_id: Optional[str] = None
    notes: Optional[str] = None


class TaskAttachmentInput(BaseModel):
    file_id: str
    file_hash: str
    user_id: Optional[str] = None


class CompetenceBatchGenerateInput(BaseModel):
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})
    organization_id: Optional[str] = None
    company_ids: Optional[List[str]] = None


class CompetenceBatchGenerateResult(BaseModel):
    competence: str
    companies_processed: int
    tasks_generated: int
    errors: List[Dict[str, str]]


class WorkloadSummaryItem(BaseModel):
    analyst_user_id: str
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    overdue_tasks: int
    critical_risk_tasks: int
