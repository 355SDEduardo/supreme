"""LGPD Compliance service handling consents and data subject rights (Art. 18)."""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from .models import PrivacyConsent, LgpdSubjectRequest


def record_consent(
    db: Session,
    user_id: str,
    term_version: str,
    ip_address: str,
    legal_basis: str = "Execucao de Contrato",
    user_agent: Optional[str] = None
) -> PrivacyConsent:
    consent = PrivacyConsent(
        user_id=user_id,
        term_version=term_version,
        legal_basis=legal_basis,
        ip_address=ip_address,
        user_agent=user_agent,
        accepted_at=datetime.now(timezone.utc),
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent


def revoke_consent(db: Session, consent_id: str) -> Optional[PrivacyConsent]:
    consent = db.query(PrivacyConsent).filter(PrivacyConsent.id == consent_id).first()
    if consent:
        consent.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(consent)
    return consent


def create_subject_request(
    db: Session,
    user_id: str,
    request_type: str,
    details: Optional[str] = None
) -> LgpdSubjectRequest:
    req = LgpdSubjectRequest(
        user_id=user_id,
        request_type=request_type,
        details=details,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def resolve_subject_request(
    db: Session,
    request_id: str,
    status: str,
    notes: Optional[str] = None
) -> Optional[LgpdSubjectRequest]:
    req = db.query(LgpdSubjectRequest).filter(LgpdSubjectRequest.id == request_id).first()
    if req:
        req.status = status
        req.response_notes = notes
        req.resolved_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(req)
    return req
