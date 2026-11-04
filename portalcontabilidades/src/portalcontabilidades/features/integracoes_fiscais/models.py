"""SQLAlchemy Models for Feature 05: Integrações Fiscais e Governamentais."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Enum, Integer, JSON
)
from portalcontabilidades.core.database import Base


class FiscalTransmission(Base):
    """Asynchronous fiscal transmissions (eSocial, EFD-Reinf, DCTFWeb, NFS-e)."""
    __tablename__ = "fiscal_transmissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    system_target = Column(
        Enum("esocial", "efd_reinf", "dctfweb", "nfse_nacional", "integra_contador", name="system_target_enum"),
        nullable=False,
        index=True
    )
    event_type = Column(String(50), nullable=False) # 'S-1200', 'R-4020', 'EMISSAO_NFSE'
    competence = Column(String(7), nullable=False, index=True)
    environment = Column(
        Enum("test_restricted", "production", name="fiscal_env_enum"),
        default="production",
        nullable=False
    )
    idempotency_key = Column(String(100), unique=True, nullable=False, index=True)
    xml_sent_payload = Column(Text, nullable=False)
    xml_response_payload = Column(Text, nullable=True)
    receipt_number = Column(String(100), nullable=True)
    status = Column(
        Enum("draft", "queued", "sending", "processing", "accepted", "rejected", "failed", name="transmission_status_enum"),
        default="queued",
        nullable=False,
        index=True
    )
    error_code = Column(String(50), nullable=True)
    error_message_raw = Column(Text, nullable=True)
    error_message_translated = Column(Text, nullable=True)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class FiscalReceipt(Base):
    """Immutable archive of official receipts returned by the tax authorities."""
    __tablename__ = "fiscal_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transmission_id = Column(String(36), nullable=False, index=True)
    company_id = Column(String(36), nullable=False, index=True)
    system_target = Column(String(50), nullable=False)
    protocol_number = Column(String(100), nullable=False)
    receipt_number = Column(String(100), nullable=False)
    receipt_xml = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
