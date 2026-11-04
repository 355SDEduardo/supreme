"""SQLAlchemy Models for Feature 02: Gestão Inteligente de Documentos."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer, BigInteger, Enum, ForeignKey, JSON
)
from portalcontabilidades.core.database import Base


class DocumentFolder(Base):
    __tablename__ = "document_folders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    competence = Column(String(7), nullable=False, index=True)  # '2026-09'
    department = Column(
        Enum("fiscal", "contabil", "rh", "financeiro", name="doc_department_enum"),
        nullable=False
    )
    folder_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    folder_id = Column(String(36), ForeignKey("document_folders.id"), nullable=True)
    company_id = Column(String(36), nullable=False, index=True)
    competence = Column(String(7), nullable=False, index=True)
    department = Column(String(50), nullable=False, default="fiscal")
    file_name = Column(String(255), nullable=False)
    storage_path = Column(String(1000), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_hash_sha256 = Column(String(64), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    is_latest = Column(Boolean, default=True, nullable=False)
    uploaded_by = Column(String(36), nullable=True)
    ingestion_source = Column(
        Enum("portal_upload", "email_inbox", "api", "whatsapp_bot", name="ingestion_source_enum"),
        default="portal_upload",
        nullable=False
    )
    status = Column(
        Enum("pending_review", "validated", "rejected", "processed", name="doc_status_enum"),
        default="validated",
        nullable=False
    )
    ocr_status = Column(
        Enum("not_applicable", "queued", "processed", "failed", name="doc_ocr_status_enum"),
        default="not_applicable",
        nullable=False
    )
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DocumentReceipt(Base):
    """Irrefutable digital proof of delivery with timestamp, IP and SHA-256."""
    __tablename__ = "document_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    receipt_code = Column(String(50), unique=True, nullable=False, index=True)
    file_hash_sha256 = Column(String(64), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    uploaded_by = Column(String(36), nullable=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    timestamp_utc = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DocumentChecklist(Base):
    __tablename__ = "document_checklists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    competence = Column(String(7), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    completion_percentage = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DocumentChecklistItem(Base):
    __tablename__ = "document_checklist_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    checklist_id = Column(String(36), ForeignKey("document_checklists.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    department = Column(String(50), nullable=False)  # fiscal, contabil, rh, financeiro
    is_required = Column(Boolean, default=True)
    is_fulfilled = Column(Boolean, default=False)
    fulfilled_by_document_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
