"""Pydantic schemas for Feature 05: Integrações Fiscais e Governamentais."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class FiscalTransmissionCreate(BaseModel):
    company_id: str
    system_target: str = Field(..., description="esocial, efd_reinf, dctfweb, nfse_nacional, integra_contador")
    event_type: str = Field(..., description="S-1200, R-4020, EMISSAO_NFSE, etc.")
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})
    environment: str = "production"  # test_restricted or production
    idempotency_key: str = Field(..., description="Unique key ensuring no duplicate transmission")
    xml_payload: str


class FiscalTransmissionResponse(BaseModel):
    id: str
    company_id: str
    system_target: str
    event_type: str
    competence: str
    environment: str
    idempotency_key: str
    receipt_number: Optional[str]
    status: str
    error_code: Optional[str]
    error_message_translated: Optional[str]
    attempts: int
    created_at: datetime


class RetryTransmissionResponse(BaseModel):
    transmission_id: str
    status: str
    message: str
    next_retry_at: Optional[datetime]


class CndStatusResponse(BaseModel):
    company_id: str
    tax_id: str
    status: str  # 'regular_certidao_negativa', 'positiva_com_efeito_de_negativa', 'irregular_debitos'
    certificate_number: str
    valid_until: datetime
    active_debits_count: int
    ecac_proxy_valid: bool


class DctfwebConsolidationInput(BaseModel):
    company_id: str
    competence: str = Field(..., json_schema_extra={"example": "2026-09"})


class DctfwebConsolidationResponse(BaseModel):
    company_id: str
    competence: str
    darf_number: str
    total_inss_previdenciario: float
    total_irrf_retencao: float
    total_pcc_retencao: float
    total_darf_amount: float
    status: str
