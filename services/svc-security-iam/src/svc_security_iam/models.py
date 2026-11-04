"""SQLAlchemy Models for Feature 10: Segurança, LGPD e Certificados Digitais."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, LargeBinary, DateTime, Enum, JSON, event
)
from svc_security_iam.database import Base


class DigitalCertificate(Base):
    __tablename__ = "digital_certificates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    certificate_type = Column(
        Enum("a1_file", "cloud_birdid", "cloud_safeweb", "ecac_proxy", name="cert_type_enum"),
        default="a1_file",
        nullable=False
    )
    # Encrypted payload with AES-256-GCM
    encrypted_certificate_payload = Column(LargeBinary, nullable=False)
    encrypted_password = Column(String(500), nullable=False)
    issued_to_tax_id = Column(String(18), nullable=False, index=True)
    common_name = Column(String(255), nullable=True)
    valid_from = Column(DateTime, nullable=False)
    valid_until = Column(DateTime, nullable=False)
    status = Column(
        Enum("active", "expired", "revoked", name="cert_status_enum"),
        default="active",
        nullable=False
    )
    warning_last_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AuditLog(Base):
    """Immutable Audit Trail. Enforced append-only."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id = Column(String(36), nullable=True, index=True)
    organization_id = Column(String(36), nullable=True, index=True)
    company_id = Column(String(36), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(36), nullable=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    payload_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# Enforce append-only on AuditLog
@event.listens_for(AuditLog, "before_update")
def prevent_audit_log_update(mapper, connection, target):
    raise PermissionError("Audit logs are strictly append-only and cannot be updated.")


@event.listens_for(AuditLog, "before_delete")
def prevent_audit_log_delete(mapper, connection, target):
    raise PermissionError("Audit logs are strictly append-only and cannot be deleted.")


class PrivacyConsent(Base):
    __tablename__ = "privacy_consents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    term_version = Column(String(20), nullable=False)
    legal_basis = Column(String(100), nullable=False, default="Execucao de Contrato")
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    accepted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class LgpdSubjectRequest(Base):
    __tablename__ = "lgpd_subject_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    request_type = Column(
        Enum("access", "confirmation", "correction", "deletion", name="lgpd_request_type_enum"),
        nullable=False
    )
    details = Column(Text, nullable=True)
    status = Column(
        Enum("pending", "in_progress", "completed", "rejected", name="lgpd_status_enum"),
        default="pending",
        nullable=False
    )
    response_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
