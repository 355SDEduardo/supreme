"""Pydantic Schemas for Feature 08: Automação e IA Contábil."""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class OcrExtractionRequest(BaseModel):
    document_id: str
    raw_text: str


class OcrExtractionResponse(BaseModel):
    extraction_id: str
    document_id: str
    extracted_data: Dict[str, Any]
    confidence_score: float
    requires_manual_review: bool
    status: str


class ClassificationSuggestionRequest(BaseModel):
    company_id: str
    description_or_memo: str
    amount: float = Field(gt=0)
    document_id: Optional[str] = None
    transaction_id: Optional[str] = None


class ClassificationSuggestionResponse(BaseModel):
    id: str
    company_id: str
    suggested_debit_account: str
    suggested_credit_account: str
    suggested_cost_center: Optional[str] = None
    suggested_narrative: str
    confidence_score: float
    decision_status: str
    requires_human_approval: bool = True
    is_learned_rule: bool = False


class FeedbackRequest(BaseModel):
    decision: str = Field(description="'accepted', 'edited', or 'rejected'")
    reviewed_by: str
    counterparty_keyword: Optional[str] = None
    edited_debit_account: Optional[str] = None
    edited_credit_account: Optional[str] = None
    edited_cost_center: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    decision_status: str
    reviewed_by: str
    reviewed_at: datetime
    message: str


class AnomalyScanRequest(BaseModel):
    company_id: str
    new_bill: Dict[str, Any]
    historical_bills: List[Dict[str, Any]] = []
    historical_average_expense: Optional[float] = None


class AnomalyAlertResponse(BaseModel):
    id: str
    company_id: str
    anomaly_type: str
    severity: str
    details: Dict[str, Any]
    dismissed: bool
    created_at: datetime


class ExecutiveSummaryRequest(BaseModel):
    company_id: str
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    metrics_summary: Optional[Dict[str, Any]] = None


class ExecutiveSummaryResponse(BaseModel):
    company_id: str
    competence: str
    summary_narrative: str
    key_highlights: List[str]
    sources_analyzed: List[str]
    legal_disclaimer: str
