"""Unit and Integration Tests for Feature 05: Integrações Fiscais e Governamentais."""


import pytest

from portalcontabilidades.features.integracoes_fiscais.models import FiscalTransmission, FiscalReceipt
from portalcontabilidades.features.integracoes_fiscais.xml_validator import validate_fiscal_xml
from portalcontabilidades.features.integracoes_fiscais.error_translator import translate_fiscal_error
from portalcontabilidades.features.integracoes_fiscais.service import (
    enqueue_fiscal_transmission, retry_transmission, consolidate_dctfweb
)
from portalcontabilidades.features.integracoes_fiscais.schemas import FiscalTransmissionCreate


def test_xml_schema_validation():
    """DoD: All transmitted XMLs must pass local validation before government connection."""
    # 1. Invalid syntax
    is_valid, err = validate_fiscal_xml("esocial", "S-1200", "<xml aberto sem fechar>")
    assert is_valid is False
    assert "sintaxe" in err.lower()

    # 2. Missing mandatory field in S-1200 (cpfTrab)
    incomplete_s1200 = """<?xml version="1.0" encoding="utf-8"?>
    <eSocial><evtRemun><ideEmpregador><nrInsc>11222333000181</nrInsc></ideEmpregador></evtRemun></eSocial>"""
    is_valid, err = validate_fiscal_xml("esocial", "S-1200", incomplete_s1200)
    assert is_valid is False
    assert "cpftrab" in err.lower()

    # 3. Valid S-1200
    valid_s1200 = """<?xml version="1.0" encoding="utf-8"?>
    <eSocial><evtRemun>
        <ideEmpregador><nrInsc>11222333000181</nrInsc></ideEmpregador>
        <ideTrabalhador><cpfTrab>12345678900</cpfTrab></ideTrabalhador>
    </evtRemun></eSocial>"""
    is_valid, err = validate_fiscal_xml("esocial", "S-1200", valid_s1200)
    assert is_valid is True
    assert err is None


def test_semantic_error_translation():
    """DoD: The system must never expose raw cryptic SOAP faults; translates to actionable Portuguese."""
    msg_401 = translate_fiscal_error("401", "Conteudo do evento invalido")
    assert "inconsistente" in msg_401.lower() or "receita federal" in msg_401.lower()

    msg_ms0015 = translate_fiscal_error("MS0015", "Period closed")
    assert "encerrada" in msg_ms0015.lower()
    assert "reabertura" in msg_ms0015.lower()

    msg_503 = translate_fiscal_error("503", "Service unavailable")
    assert "indisponíveis" in msg_503.lower() or "retentativa" in msg_503.lower()


def test_idempotency_enforcement(db_session):
    """DoD: Enforces idempotency_key to prevent duplicate tax submissions."""
    valid_xml = """<?xml version="1.0"?>
    <eSocial><evtRemun><ideEmpregador><nrInsc>111</nrInsc></ideEmpregador><ideTrabalhador><cpfTrab>222</cpfTrab></ideTrabalhador></evtRemun></eSocial>"""

    payload = FiscalTransmissionCreate(
        company_id="comp-fisc-01",
        system_target="esocial",
        event_type="S-1200",
        competence="2026-09",
        idempotency_key="idemp-key-unique-9988",
        xml_payload=valid_xml
    )

    t1 = enqueue_fiscal_transmission(db_session, payload)
    assert t1.status == "accepted"
    assert t1.receipt_number is not None

    # Resend identical transmission with same idempotency key
    t2 = enqueue_fiscal_transmission(db_session, payload)
    assert t2.id == t1.id  # Same instance returned without duplicate filing
    assert db_session.query(FiscalTransmission).count() == 1


def test_resilient_backoff_on_transient_failure(db_session):
    """Validates exponential backoff schedule when simulated government 503 instability occurs."""
    instability_xml = """<?xml version="1.0"?>
    <eSocial><evtRemun>
        <ideEmpregador><nrInsc>111</nrInsc></ideEmpregador>
        <ideTrabalhador><cpfTrab>222</cpfTrab></ideTrabalhador>
        <simular_instabilidade_503/>
    </evtRemun></eSocial>"""

    payload = FiscalTransmissionCreate(
        company_id="comp-fisc-01",
        system_target="esocial",
        event_type="S-1200",
        competence="2026-09",
        idempotency_key="idemp-backoff-test",
        xml_payload=instability_xml
    )

    trans = enqueue_fiscal_transmission(db_session, payload)
    assert trans.status == "queued"
    assert trans.error_code == "503"
    assert trans.next_retry_at is not None
    assert "indisponíveis" in trans.error_message_translated.lower()


def test_dctfweb_darf_consolidation(db_session):
    """Validates unified DARF consolidation from social security and withholding taxes."""
    darf_res = consolidate_dctfweb(db_session, "comp-fisc-01", "2026-09")
    assert darf_res.darf_number.startswith("DARF-202609-")
    assert darf_res.total_darf_amount > 0
    assert darf_res.total_darf_amount == (
        darf_res.total_inss_previdenciario + darf_res.total_irrf_retencao + darf_res.total_pcc_retencao
    )
