"""Service logic for Feature 05: Integrações Fiscais e Governamentais."""
import uuid

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import FiscalTransmission, FiscalReceipt
from .schemas import (
    FiscalTransmissionCreate, FiscalTransmissionResponse,
    RetryTransmissionResponse, CndStatusResponse, DctfwebConsolidationResponse
)
from .xml_validator import validate_fiscal_xml
from .error_translator import translate_fiscal_error

BACKOFF_MINUTES = [1, 5, 15, 60]


def enqueue_fiscal_transmission(
    db: Session,
    data: FiscalTransmissionCreate
) -> FiscalTransmission:
    """Enqueues fiscal event with strict idempotency and local schema pre-validation."""
    # 1. Idempotency Enforcement (DoD)
    existing = db.query(FiscalTransmission).filter(
        FiscalTransmission.idempotency_key == data.idempotency_key
    ).first()
    if existing:
        return existing

    # 2. Local XML Schema Validation before Web Service transmission
    is_valid_xml, xml_err = validate_fiscal_xml(data.system_target, data.event_type, data.xml_payload)

    transmission = FiscalTransmission(
        company_id=data.company_id,
        system_target=data.system_target,
        event_type=data.event_type,
        competence=data.competence,
        environment=data.environment,
        idempotency_key=data.idempotency_key,
        xml_sent_payload=data.xml_payload,
        status="queued" if is_valid_xml else "rejected",
        error_code="SCHEMA_INVALID" if not is_valid_xml else None,
        error_message_raw=xml_err if not is_valid_xml else None,
        error_message_translated=xml_err if not is_valid_xml else None,
        attempts=0,
        created_at=datetime.now(timezone.utc)
    )
    db.add(transmission)
    db.flush()

    if not is_valid_xml:
        db.commit()
        db.refresh(transmission)
        return transmission

    # 3. Simulate Worker Processing & Government Web Service Transmission
    _process_transmission_attempt(db, transmission)
    db.commit()
    db.refresh(transmission)
    return transmission


def _process_transmission_attempt(db: Session, trans: FiscalTransmission) -> None:
    """Simulates XMLDSig signature and government web service response with backoff on network failures."""
    trans.attempts += 1
    trans.last_attempt_at = datetime.now(timezone.utc)

    # Check for simulated errors in test payloads
    payload_lower = trans.xml_sent_payload.lower()
    if "simular_erro_401" in payload_lower:
        trans.status = "rejected"
        trans.error_code = "401"
        trans.error_message_raw = "Codigo 401 - Conteudo do evento invalido: [nrInsc]"
        trans.error_message_translated = translate_fiscal_error("401", trans.error_message_raw)
        return

    if "simular_instabilidade_503" in payload_lower:
        trans.status = "queued"
        trans.error_code = "503"
        trans.error_message_raw = "HTTP 503 Service Unavailable"
        trans.error_message_translated = translate_fiscal_error("503", trans.error_message_raw)
        # Apply exponential backoff
        backoff_idx = min(trans.attempts - 1, len(BACKOFF_MINUTES) - 1)
        trans.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=BACKOFF_MINUTES[backoff_idx])
        return

    # Normal success path: Accepted by Government Fisco
    protocol = f"PROT-{trans.competence.replace('-', '')}-{uuid.uuid4().hex[:10].upper()}"
    receipt_no = f"REC-{uuid.uuid4().hex[:12].upper()}"

    trans.status = "accepted"
    trans.receipt_number = receipt_no
    trans.xml_response_payload = f"<retorno><status>200</status><protocolo>{protocol}</protocolo><recibo>{receipt_no}</recibo></retorno>"

    receipt = FiscalReceipt(
        transmission_id=trans.id,
        company_id=trans.company_id,
        system_target=trans.system_target,
        protocol_number=protocol,
        receipt_number=receipt_no,
        receipt_xml=trans.xml_response_payload,
        created_at=datetime.now(timezone.utc)
    )
    db.add(receipt)


def retry_transmission(db: Session, transmission_id: str) -> RetryTransmissionResponse:
    """Manual retry for corrected rejected or failed transmissions."""
    trans = db.query(FiscalTransmission).filter(FiscalTransmission.id == transmission_id).first()
    if not trans:
        raise HTTPException(status_code=404, detail="Transmissão fiscal não encontrada.")

    trans.status = "queued"
    trans.error_code = None
    trans.error_message_raw = None
    trans.error_message_translated = None

    _process_transmission_attempt(db, trans)
    db.commit()

    return RetryTransmissionResponse(
        transmission_id=trans.id,
        status=trans.status,
        message="Retentativa executada.",
        next_retry_at=trans.next_retry_at
    )


def consolidate_dctfweb(db: Session, company_id: str, competence: str) -> DctfwebConsolidationResponse:
    """Consolidates social security and tax withholdings into a single unified DARF."""
    # Simulation: eSocial INSS + EFD-Reinf IRRF & PCC
    inss = 3450.80
    irrf = 1200.00
    pcc = 465.50
    total = inss + irrf + pcc

    darf_num = f"DARF-{competence.replace('-', '')}-{uuid.uuid4().hex[:6].upper()}"
    return DctfwebConsolidationResponse(
        company_id=company_id,
        competence=competence,
        darf_number=darf_num,
        total_inss_previdenciario=inss,
        total_irrf_retencao=irrf,
        total_pcc_retencao=pcc,
        total_darf_amount=total,
        status="gerado_aguardando_pagamento"
    )
