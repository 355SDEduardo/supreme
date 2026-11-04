"""Unit and Integration Tests for Feature 02: Gestão Inteligente de Documentos."""


import pytest
from fastapi import HTTPException

from portalcontabilidades.features.documentos.models import Document, DocumentReceipt, DocumentChecklist, DocumentChecklistItem
from portalcontabilidades.features.documentos.file_validator import calculate_sha256, validate_file_safety
from portalcontabilidades.features.documentos.service import (
    process_document_upload, get_or_create_monthly_checklist
)


def test_sha256_calculation():
    """Validates SHA-256 integrity."""
    data = b"Extrato Bancario OFX Banco do Brasil 2026-09"
    hash_val = calculate_sha256(data)
    assert len(hash_val) == 64
    assert hash_val == calculate_sha256(data)


def test_executable_and_disguised_file_blocking():
    """DoD: Executable files and PE headers must be blocked immediately."""
    # 1. Blocked extension
    safe, msg = validate_file_safety("malware.exe", b"Some random content")
    assert safe is False
    assert "proibida" in msg.lower()

    safe, msg = validate_file_safety("script.bat", b"echo off")
    assert safe is False

    # 2. Disguised executable (PE header with .pdf extension)
    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100
    safe, msg = validate_file_safety("falso_recibo.pdf", fake_pdf)
    assert safe is False
    assert "camuflado" in msg.lower()

    # 3. Legitimate PDF
    real_pdf = b"%PDF-1.4\n%real content here..."
    safe, msg = validate_file_safety("relatorio_mensal.pdf", real_pdf)
    assert safe is True


def test_document_receipt_generation(db_session):
    """DoD: Every ingested file must generate an immutable DocumentReceipt with code, IP, and SHA-256."""
    pdf_content = b"%PDF-1.7\nNota Fiscal de Servico Eletronica..."
    doc, receipt, is_dup = process_document_upload(
        db=db_session,
        company_id="comp-10",
        competence="2026-09",
        department="fiscal",
        file_name="nfse_setembro.pdf",
        file_content=pdf_content,
        ip_address="187.120.40.2"
    )
    assert is_dup is False
    assert doc.id is not None
    assert receipt.receipt_code.startswith("REC-202609-")
    assert receipt.file_hash_sha256 == calculate_sha256(pdf_content)
    assert receipt.ip_address == "187.120.40.2"


def test_deduplication_detection(db_session):
    """DoD: Ingesting the identical file hash in the same company and competence triggers deduplication."""
    content = b"%PDF-1.5\nExtrato Bancario Itau..."
    doc1, receipt1, is_dup1 = process_document_upload(
        db=db_session,
        company_id="comp-10",
        competence="2026-09",
        department="financeiro",
        file_name="extrato_itau.pdf",
        file_content=content
    )
    assert is_dup1 is False

    # Second upload with same content and different filename
    doc2, receipt2, is_dup2 = process_document_upload(
        db=db_session,
        company_id="comp-10",
        competence="2026-09",
        department="financeiro",
        file_name="extrato_itau_copia.pdf",
        file_content=content
    )
    assert is_dup2 is True
    assert doc2.id == doc1.id


def test_native_versioning(db_session):
    """DoD: Uploading an edited file with the same name promotes version N+1 and marks old version as is_latest=False."""
    v1_content = b"%PDF-1.4\nPlanilha Versao 1..."
    doc_v1, _, _ = process_document_upload(
        db=db_session,
        company_id="comp-10",
        competence="2026-09",
        department="contabil",
        file_name="balancete.pdf",
        file_content=v1_content
    )
    assert doc_v1.version == 1
    assert doc_v1.is_latest is True

    # Upload updated version with same filename
    v2_content = b"%PDF-1.4\nPlanilha Versao 2 Atualizada com Ajustes..."
    doc_v2, _, _ = process_document_upload(
        db=db_session,
        company_id="comp-10",
        competence="2026-09",
        department="contabil",
        file_name="balancete.pdf",
        file_content=v2_content
    )
    assert doc_v2.version == 2
    assert doc_v2.is_latest is True

    # Verify old version archived
    db_session.refresh(doc_v1)
    assert doc_v1.version == 1
    assert doc_v1.is_latest is False


def test_checklist_progress_tracking(db_session):
    """Validates that document checklist completion percentage increases upon file ingestion."""
    checklist = get_or_create_monthly_checklist(db_session, "comp-checklist-01", "2026-09")
    initial_pct = checklist.completion_percentage
    assert initial_pct == 0

    # Upload financial document
    process_document_upload(
        db=db_session,
        company_id="comp-checklist-01",
        competence="2026-09",
        department="financeiro",
        file_name="extrato.pdf",
        file_content=b"%PDF-1.4\nExtrato..."
    )

    db_session.refresh(checklist)
    assert checklist.completion_percentage > initial_pct
