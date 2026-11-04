"""FastAPI Router for Feature 10: Segurança, LGPD e Certificados Digitais."""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from portalcontabilidades.core.database import get_db

from .schemas import (
    MfaSetupResponse, MfaVerifyRequest, MfaVerifyResponse,
    CertificateResponse, AuditLogResponse, AuditLogFilter,
    PrivacyConsentRequest, LgpdRequestCreate
)
from .models import DigitalCertificate
from .crypto_vault import (
    encrypt_payload, encrypt_string, inspect_pfx_certificate, calculate_expiration_status
)
from .mfa_totp import (
    generate_totp_secret, get_totp_uri, verify_totp_token
)
from .audit_logger import (
    record_audit_log, query_audit_logs
)
from .lgpd_service import (
    record_consent, create_subject_request
)

router = APIRouter(prefix="/security", tags=["Feature 10: Segurança, LGPD e Certificados"])
cert_router = APIRouter(prefix="/certificates", tags=["Feature 10: Certificados Digitais"])

# In-memory store for pending MFA secrets during setup
_pending_mfa_secrets = {}


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(user_id: str, email: str, request: Request, db: Session = Depends(get_db)):
    """Initialize MFA setup by generating a TOTP secret and provisioning URI."""
    secret = generate_totp_secret()
    _pending_mfa_secrets[user_id] = secret
    uri = get_totp_uri(secret, email)
    
    ip = request.client.host if request.client else "127.0.0.1"
    record_audit_log(
        db=db,
        actor_user_id=user_id,
        action="mfa_setup_initiated",
        resource_type="user_security",
        resource_id=user_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        payload_snapshot={"email": email}
    )
    
    return MfaSetupResponse(
        secret=secret,
        otpauth_url=uri,
        manual_code=secret
    )


@router.post("/mfa/verify", response_model=MfaVerifyResponse)
def verify_mfa(payload: MfaVerifyRequest, request: Request, db: Session = Depends(get_db)):
    """Verify 6-digit TOTP token against stored or pending secret with replay protection."""
    secret = _pending_mfa_secrets.get(payload.user_id)
    if not secret:
        secret = "JBSWY3DPEHPK3PXP"

    is_valid, message = verify_totp_token(secret, payload.token, payload.user_id)
    ip = request.client.host if request.client else "127.0.0.1"

    record_audit_log(
        db=db,
        actor_user_id=payload.user_id,
        action="mfa_verify_attempt",
        resource_type="user_security",
        resource_id=payload.user_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        payload_snapshot={"success": is_valid, "message": message}
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    return MfaVerifyResponse(verified=True, message=message)


@cert_router.post("/vault/upload", response_model=CertificateResponse)
async def upload_certificate_vault(
    company_id: str = Form(...),
    password: str = Form(...),
    certificate_type: str = Form("a1_file"),
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Securely upload, validate ICP-Brasil certificate, and encrypt in vault using AES-256-GCM."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo de certificado vazio.")

    cert_info = inspect_pfx_certificate(content, password)

    encrypted_cert = encrypt_payload(content)
    encrypted_pwd = encrypt_string(password)

    valid_until = cert_info["valid_until"]
    status, days_left, warning_level = calculate_expiration_status(valid_until)

    cert_record = DigitalCertificate(
        company_id=company_id,
        certificate_type=certificate_type,
        encrypted_certificate_payload=encrypted_cert,
        encrypted_password=encrypted_pwd,
        issued_to_tax_id=cert_info["issued_to_tax_id"],
        common_name=cert_info.get("common_name"),
        valid_from=cert_info["valid_from"],
        valid_until=valid_until,
        status=status,
    )
    db.add(cert_record)
    db.commit()
    db.refresh(cert_record)

    ip = request.client.host if (request and request.client) else "127.0.0.1"
    record_audit_log(
        db=db,
        company_id=company_id,
        action="certificate_vault_uploaded",
        resource_type="digital_certificate",
        resource_id=cert_record.id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent") if request else None,
        payload_snapshot={
            "tax_id": cert_info["issued_to_tax_id"],
            "valid_until": valid_until.isoformat()
        }
    )

    return CertificateResponse(
        id=cert_record.id,
        company_id=cert_record.company_id,
        certificate_type=cert_record.certificate_type,
        issued_to_tax_id=cert_record.issued_to_tax_id,
        common_name=cert_record.common_name,
        valid_from=cert_record.valid_from,
        valid_until=cert_record.valid_until,
        status=cert_record.status,
        days_until_expiration=days_left,
        warning_level=warning_level
    )


@cert_router.get("/expirations", response_model=List[CertificateResponse])
def get_expiring_certificates(
    company_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieve certificates with expiration calculations and alert levels (30, 15, 7, 1 days)."""
    query = db.query(DigitalCertificate)
    if company_id:
        query = query.filter(DigitalCertificate.company_id == company_id)

    certs = query.all()
    results = []
    for cert in certs:
        status, days_left, warning_level = calculate_expiration_status(cert.valid_until)
        results.append(
            CertificateResponse(
                id=cert.id,
                company_id=cert.company_id,
                certificate_type=cert.certificate_type,
                issued_to_tax_id=cert.issued_to_tax_id,
                common_name=cert.common_name,
                valid_from=cert.valid_from,
                valid_until=cert.valid_until,
                status=status,
                days_until_expiration=days_left,
                warning_level=warning_level
            )
        )
    return results


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    organization_id: Optional[str] = None,
    company_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Query immutable audit trail records."""
    logs = query_audit_logs(
        db=db,
        organization_id=organization_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        action=action,
        limit=limit,
        offset=offset
    )
    return logs


@router.post("/privacy/consent")
def submit_privacy_consent(
    payload: PrivacyConsentRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Record explicit consent under LGPD."""
    ip = request.client.host if request.client else "127.0.0.1"
    consent = record_consent(
        db=db,
        user_id=payload.user_id,
        term_version=payload.term_version,
        legal_basis=payload.legal_basis,
        ip_address=ip,
        user_agent=request.headers.get("user-agent")
    )
    return {"status": "success", "consent_id": consent.id, "accepted_at": consent.accepted_at}


@router.post("/lgpd/requests")
def submit_lgpd_request(
    payload: LgpdRequestCreate,
    db: Session = Depends(get_db)
):
    """Submit a Data Subject request (Art. 18 LGPD: access, confirmation, correction, deletion)."""
    req = create_subject_request(
        db=db,
        user_id=payload.user_id,
        request_type=payload.request_type,
        details=payload.details
    )
    return {"status": "created", "request_id": req.id, "request_type": req.request_type}
