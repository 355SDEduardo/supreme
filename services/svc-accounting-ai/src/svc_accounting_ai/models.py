"""SQLAlchemy Models for Feature 08: Automação e IA Contábil."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Numeric, Enum, ForeignKey, Boolean, Integer, JSON
)
from svc_accounting_ai.database import Base


class AiExtraction(Base):
    __tablename__ = "ai_extractions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), nullable=False, index=True)
    model_version = Column(String(100), default="ocr-extractor-v1.2")
    raw_extracted_json = Column(JSON, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False) # e.g. 96.50
    processing_time_ms = Column(Integer, default=150)
    status = Column(Enum("queued", "completed", "failed", name="ai_extract_status_enum"), default="completed")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AiClassificationSuggestion(Base):
    __tablename__ = "ai_classification_suggestions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    transaction_id = Column(String(36), nullable=True, index=True)
    document_id = Column(String(36), nullable=True, index=True)
    suggested_debit_account = Column(String(100), nullable=False)
    suggested_credit_account = Column(String(100), nullable=False)
    suggested_cost_center = Column(String(100), nullable=True)
    suggested_narrative = Column(Text, nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False)
    decision_status = Column(
        Enum("pending_review", "accepted", "edited", "rejected", name="ai_decision_status_enum"),
        default="pending_review",
        nullable=False,
        index=True
    )
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    final_classification_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AiAnomalyAlert(Base):
    __tablename__ = "ai_anomaly_alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    anomaly_type = Column(
        Enum("duplicate_payment_risk", "tax_retention_mismatch", "abnormal_expense_spike", "missing_recurring_expense", name="ai_anomaly_type_enum"),
        nullable=False,
        index=True
    )
    severity = Column(Enum("info", "warning", "critical", name="anomaly_severity_enum"), default="warning")
    details = Column(JSON, nullable=False)
    dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
