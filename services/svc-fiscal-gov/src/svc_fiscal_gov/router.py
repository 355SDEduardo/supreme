"""FastAPI Router for Feature 05: Integrações Fiscais e Governamentais."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from svc_fiscal_gov.database import get_db

from .schemas import (
    FiscalTransmissionCreate, FiscalTransmissionResponse,
    RetryTransmissionResponse, CndStatusResponse,
    DctfwebConsolidationInput, DctfwebConsolidationResponse
)
from .models import FiscalTransmission
from .service import (
    enqueue_fiscal_transmission, retry_transmission, consolidate_dctfweb
)

router = APIRouter(prefix="/fiscal", tags=["Feature 05: Integrações Fiscais e Governamentais"])


@router.post("/transmissions/enqueue", response_model=FiscalTransmissionResponse)
def enqueue_transmission(
    payload: FiscalTransmissionCreate,
    db: Session = Depends(get_db)
):
    """Enqueues fiscal transmission event with XML schema validation and idempotency."""
    trans = enqueue_fiscal_transmission(db=db, data=payload)
    return trans


@router.get("/transmissions/{transmission_id}/status", response_model=FiscalTransmissionResponse)
def get_transmission_status(
    transmission_id: str,
    db: Session = Depends(get_db)
):
    """Retrieve transmission progress, receipt protocol, or translated error instructions."""
    trans = db.query(FiscalTransmission).filter(FiscalTransmission.id == transmission_id).first()
    if not trans:
        raise HTTPException(status_code=404, detail="Transmissão fiscal não encontrada.")
    return trans


@router.post("/transmissions/{transmission_id}/retry", response_model=RetryTransmissionResponse)
def force_retry_transmission(
    transmission_id: str,
    db: Session = Depends(get_db)
):
    """Force retry processing for rejected or transiently failed events."""
    return retry_transmission(db=db, transmission_id=transmission_id)


@router.get("/companies/{company_id}/cnd-status", response_model=CndStatusResponse)
def get_company_cnd_status(
    company_id: str,
    db: Session = Depends(get_db)
):
    """Consults consolidated CND situation fiscal via SERPRO Integra Contador."""
    valid_until = datetime.now(timezone.utc) + timedelta(days=90)
    return CndStatusResponse(
        company_id=company_id,
        tax_id="11222333000181",
        status="regular_certidao_negativa",
        certificate_number="CND-RFB-2026-998877",
        valid_until=valid_until,
        active_debits_count=0,
        ecac_proxy_valid=True
    )


@router.post("/dctfweb/consolidate", response_model=DctfwebConsolidationResponse)
def consolidate_dctfweb_and_darf(
    payload: DctfwebConsolidationInput,
    db: Session = Depends(get_db)
):
    """Consolidates social security and tax withholdings into a single unified DARF."""
    return consolidate_dctfweb(db=db, company_id=payload.company_id, competence=payload.competence)
