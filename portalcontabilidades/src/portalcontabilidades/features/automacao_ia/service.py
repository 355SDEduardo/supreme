"""Business service for Feature 08: Automação e IA Contábil."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session


from .models import AiExtraction, AiClassificationSuggestion, AiAnomalyAlert
from .ocr_extractor import extract_structured_invoice_data
from .classification_suggester import suggest_accounting_classification, register_user_feedback
from .anomaly_detector import detect_payment_anomalies
from .executive_summary import generate_consultative_summary


def process_ocr_document(db: Session, document_id: str, raw_text: str) -> AiExtraction:
    """Processes OCR text, extracts metadata, saves to database."""
    extracted = extract_structured_invoice_data(raw_text)
    record = AiExtraction(
        document_id=document_id,
        model_version="ocr-extractor-v1.2",
        raw_extracted_json=extracted,
        confidence_score=Decimal(str(extracted["confidence_score"])),
        processing_time_ms=180,
        status="completed"
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def generate_classification_suggestion(
    db: Session,
    company_id: str,
    description_or_memo: str,
    amount: float,
    document_id: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> AiClassificationSuggestion:
    """Predicts debit/credit classification with confidence score."""
    pred = suggest_accounting_classification(company_id, description_or_memo, amount)
    suggestion = AiClassificationSuggestion(
        company_id=company_id,
        transaction_id=transaction_id,
        document_id=document_id,
        suggested_debit_account=pred["suggested_debit_account"],
        suggested_credit_account=pred["suggested_credit_account"],
        suggested_cost_center=pred.get("suggested_cost_center"),
        suggested_narrative=pred["suggested_narrative"],
        confidence_score=Decimal(str(pred["confidence_score"])),
        decision_status="pending_review"
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def apply_operator_feedback(
    db: Session,
    suggestion_id: str,
    decision: str,
    reviewed_by: str,
    counterparty_keyword: Optional[str] = None,
    edited_debit_account: Optional[str] = None,
    edited_credit_account: Optional[str] = None,
    edited_cost_center: Optional[str] = None
) -> AiClassificationSuggestion:
    """Records human operator decision and feeds the continuous learning loop."""
    sugg = db.query(AiClassificationSuggestion).filter(AiClassificationSuggestion.id == suggestion_id).first()
    if not sugg:
        raise ValueError(f"Sugestão de IA não encontrada: {suggestion_id}")

    sugg.decision_status = decision
    sugg.reviewed_by = reviewed_by
    sugg.reviewed_at = datetime.now(timezone.utc)

    final_debit = edited_debit_account or sugg.suggested_debit_account
    final_credit = edited_credit_account or sugg.suggested_credit_account
    final_cc = edited_cost_center or sugg.suggested_cost_center

    sugg.final_classification_data = {
        "debit": final_debit,
        "credit": final_credit,
        "cost_center": final_cc
    }

    # If the user edited or registered a specific feedback keyword, train the learning loop
    if decision in ["edited", "accepted"] and counterparty_keyword:
        register_user_feedback(
            company_id=sugg.company_id,
            counterparty_keyword=counterparty_keyword,
            debit_account=final_debit,
            credit_account=final_credit,
            cost_center=final_cc or "ADM"
        )

    db.commit()
    db.refresh(sugg)
    return sugg


def scan_and_record_anomalies(
    db: Session,
    company_id: str,
    new_bill: Dict[str, Any],
    historical_bills: List[Dict[str, Any]],
    historical_avg_expense: Optional[float] = None
) -> List[AiAnomalyAlert]:
    """Detects anomalies and persists alert records."""
    avg_dec = Decimal(str(historical_avg_expense)) if historical_avg_expense else None
    detected = detect_payment_anomalies(new_bill, historical_bills, avg_dec)
    alerts = []
    for alert_data in detected:
        alert = AiAnomalyAlert(
            company_id=company_id,
            anomaly_type=alert_data["type"],
            severity=alert_data["severity"],
            details=alert_data,
            dismissed=False
        )
        db.add(alert)
        alerts.append(alert)
    db.commit()
    for a in alerts:
        db.refresh(a)
    return alerts


def list_company_anomalies(db: Session, company_id: str) -> List[AiAnomalyAlert]:
    """Returns all anomaly alerts for a company."""
    return db.query(AiAnomalyAlert).filter(
        AiAnomalyAlert.company_id == company_id,
        AiAnomalyAlert.dismissed.is_(False)
    ).all()


def build_executive_summary(
    company_id: str,
    month: int,
    year: int,
    metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generates monthly executive draft narrative."""
    metrics_data = metrics or {
        "gross_revenue": 150000.0,
        "net_result": 32000.0,
        "final_cash_balance": 87500.0
    }
    return generate_consultative_summary(company_id, month, year, metrics_data)
