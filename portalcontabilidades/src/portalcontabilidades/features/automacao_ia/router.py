"""FastAPI Router for Feature 08: Automação e IA Contábil."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session


from portalcontabilidades.core.database import get_db
from .schemas import (
    OcrExtractionRequest, OcrExtractionResponse,
    ClassificationSuggestionRequest, ClassificationSuggestionResponse,
    FeedbackRequest, FeedbackResponse,
    AnomalyScanRequest, AnomalyAlertResponse,
    ExecutiveSummaryRequest, ExecutiveSummaryResponse
)
from . import service

router = APIRouter(prefix="/api/v1/ai", tags=["Automação e IA Contábil"])


@router.post("/documents/{document_id}/extract", response_model=OcrExtractionResponse, status_code=status.HTTP_201_CREATED)
def extract_document(
    document_id: str,
    payload: OcrExtractionRequest,
    db: Session = Depends(get_db)
):
    """Executes intelligent OCR data extraction on document text."""
    try:
        rec = service.process_ocr_document(db, document_id, payload.raw_text)
        return OcrExtractionResponse(
            extraction_id=rec.id,
            document_id=rec.document_id,
            extracted_data=rec.raw_extracted_json,
            confidence_score=float(rec.confidence_score),
            requires_manual_review=rec.raw_extracted_json.get("requires_manual_review", False),
            status=rec.status
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/transactions/suggest-classification", response_model=ClassificationSuggestionResponse)
def suggest_classification(
    payload: ClassificationSuggestionRequest,
    db: Session = Depends(get_db)
):
    """Suggests Chart of Accounts debit and credit entries with numerical confidence score."""
    try:
        sugg = service.generate_classification_suggestion(
            db,
            company_id=payload.company_id,
            description_or_memo=payload.description_or_memo,
            amount=payload.amount,
            document_id=payload.document_id,
            transaction_id=payload.transaction_id
        )
        return ClassificationSuggestionResponse(
            id=sugg.id,
            company_id=sugg.company_id,
            suggested_debit_account=sugg.suggested_debit_account,
            suggested_credit_account=sugg.suggested_credit_account,
            suggested_cost_center=sugg.suggested_cost_center,
            suggested_narrative=sugg.suggested_narrative,
            confidence_score=float(sugg.confidence_score),
            decision_status=sugg.decision_status,
            requires_human_approval=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/suggestions/{suggestion_id}/feedback", response_model=FeedbackResponse)
def register_feedback(
    suggestion_id: str,
    payload: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """Registers human operator approval or correction, updating the continuous learning cycle."""
    try:
        updated = service.apply_operator_feedback(
            db=db,
            suggestion_id=suggestion_id,
            decision=payload.decision,
            reviewed_by=payload.reviewed_by,
            counterparty_keyword=payload.counterparty_keyword,
            edited_debit_account=payload.edited_debit_account,
            edited_credit_account=payload.edited_credit_account,
            edited_cost_center=payload.edited_cost_center
        )
        return FeedbackResponse(
            id=updated.id,
            decision_status=updated.decision_status,
            reviewed_by=updated.reviewed_by,
            reviewed_at=updated.reviewed_at,
            message="Feedback do operador registrado com sucesso no ciclo de aprendizado."
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/companies/{company_id}/anomalies", response_model=List[AnomalyAlertResponse])
def get_anomalies(
    company_id: str,
    db: Session = Depends(get_db)
):
    """Lists predictive inconsistency and duplicate alerts detected for a company."""
    alerts = service.list_company_anomalies(db, company_id)
    return [
        AnomalyAlertResponse(
            id=a.id,
            company_id=a.company_id,
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            details=a.details,
            dismissed=a.dismissed,
            created_at=a.created_at
        )
        for a in alerts
    ]


@router.post("/companies/{company_id}/scan-anomalies", response_model=List[AnomalyAlertResponse])
def scan_anomalies(
    company_id: str,
    payload: AnomalyScanRequest,
    db: Session = Depends(get_db)
):
    """Runs a predictive anomaly scan on incoming bills against historical data."""
    try:
        alerts = service.scan_and_record_anomalies(
            db=db,
            company_id=company_id,
            new_bill=payload.new_bill,
            historical_bills=payload.historical_bills,
            historical_avg_expense=payload.historical_average_expense
        )
        return [
            AnomalyAlertResponse(
                id=a.id,
                company_id=a.company_id,
                anomaly_type=a.anomaly_type,
                severity=a.severity,
                details=a.details,
                dismissed=a.dismissed,
                created_at=a.created_at
            )
            for a in alerts
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/companies/{company_id}/generate-executive-summary", response_model=ExecutiveSummaryResponse)
def generate_summary(
    company_id: str,
    payload: ExecutiveSummaryRequest,
    db: Session = Depends(get_db)
):
    """Generates monthly executive draft narrative for accountant review with mandatory legal disclaimer."""
    try:
        res = service.build_executive_summary(
            company_id=company_id,
            month=payload.month,
            year=payload.year,
            metrics=payload.metrics_summary
        )
        return ExecutiveSummaryResponse(**res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
