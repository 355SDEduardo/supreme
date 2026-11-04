"""Pydantic schemas for Feature 04: Contas a Pagar e Receber."""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BillCreate(BaseModel):
    company_id: str
    type: str = Field("payable", description="payable or receivable")
    counterparty_name: str
    counterparty_tax_id: Optional[str] = None
    category_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    document_number: Optional[str] = None
    original_amount: float = Field(gt=0, allow_inf_nan=False)
    discount_amount: float = Field(0, ge=0, allow_inf_nan=False)
    interest_penalty_amount: float = Field(0, ge=0, allow_inf_nan=False)
    issue_date: date
    due_date: date
    payment_method: str = "boleto"  # boleto, pix, ted, card
    barcode_line: Optional[str] = None
    pix_key: Optional[str] = None
    pix_emv_payload: Optional[str] = None


class BillResponse(BaseModel):
    id: str
    company_id: str
    type: str
    counterparty_name: str
    counterparty_tax_id: Optional[str]
    document_number: Optional[str]
    original_amount: float
    final_amount: float
    issue_date: date
    due_date: date
    payment_date: Optional[date]
    payment_method: str
    barcode_line: Optional[str]
    pix_key: Optional[str]
    status: str
    required_approvals: int
    current_approvals: int
    rejection_reason: Optional[str]
    created_at: datetime


class BillApprovalInput(BaseModel):
    user_id: str
    user_role: str = "client_admin"
    comments: Optional[str] = None


class BillRejectInput(BaseModel):
    user_id: str
    reason: str = Field(..., min_length=5, description="Motivo obrigatório da rejeição")


class AgingListResponse(BaseModel):
    reference_date: str
    total_receivables: float
    total_overdue: float
    default_rate_pct: float
    to_expire: Dict[str, float]
    overdue: Dict[str, float]


class ReminderDispatchInput(BaseModel):
    channel: str = "whatsapp"  # whatsapp, email
