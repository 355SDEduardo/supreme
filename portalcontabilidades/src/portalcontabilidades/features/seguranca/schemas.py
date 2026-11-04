"""Pydantic schemas for Feature 10."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_code_svg: Optional[str] = None
    manual_code: str


class MfaVerifyRequest(BaseModel):
    user_id: str
    token: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")


class MfaVerifyResponse(BaseModel):
    verified: bool
    message: str


class CertificateUploadRequest(BaseModel):
    company_id: str
    password: str
    certificate_type: str = "a1_file"


class CertificateResponse(BaseModel):
    id: str
    company_id: str
    certificate_type: str
    issued_to_tax_id: str
    common_name: Optional[str]
    valid_from: datetime
    valid_until: datetime
    status: str
    days_until_expiration: int
    warning_level: Optional[str] = None  # '30_days', '15_days', '7_days', '1_day', 'expired'


class AuditLogFilter(BaseModel):
    organization_id: Optional[str] = None
    company_id: Optional[str] = None
    actor_user_id: Optional[str] = None
    action: Optional[str] = None
    limit: int = 50
    offset: int = 0


class AuditLogResponse(BaseModel):
    id: str
    actor_user_id: Optional[str]
    organization_id: Optional[str]
    company_id: Optional[str]
    action: str
    resource_type: str
    resource_id: Optional[str]
    ip_address: str
    user_agent: Optional[str]
    payload_snapshot: Optional[Dict[str, Any]]
    created_at: datetime


class PrivacyConsentRequest(BaseModel):
    user_id: str
    term_version: str
    legal_basis: str = "Execucao de Contrato"


class LgpdRequestCreate(BaseModel):
    user_id: str
    request_type: str  # access, confirmation, correction, deletion
    details: Optional[str] = None
