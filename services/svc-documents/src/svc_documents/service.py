"""Service logic for Feature 02: Gestão Inteligente de Documentos."""
import uuid
import mimetypes

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import Document, DocumentReceipt, DocumentFolder, DocumentChecklist, DocumentChecklistItem
from .file_validator import validate_file_safety, calculate_sha256
from svc_documents.config import settings


def process_document_upload(
    db: Session,
    company_id: str,
    competence: str,
    department: str,
    file_name: str,
    file_content: bytes,
    uploaded_by: Optional[str] = None,
    ip_address: str = "127.0.0.1",
    user_agent: Optional[str] = None,
    ingestion_source: str = "portal_upload"
) -> Tuple[Document, DocumentReceipt, bool]:
    """Processes document upload with validation, SHA-256 hash, deduplication, versioning, and receipt generation.
    Returns: (Document, DocumentReceipt, is_duplicate).
    """
    from supreme_common.competence import normalize_competencia
    from pathlib import Path
    competence = normalize_competencia(competence)
    file_name = Path(file_name.replace('\\','/')).name
    if department not in {'fiscal','contabil','rh','financeiro'}:
        raise HTTPException(422,'Departamento inválido.')
    # 1. Security & Magic Number validation
    is_safe, error_msg = validate_file_safety(file_name, file_content)
    if not is_safe:
        raise HTTPException(status_code=400, detail=error_msg)

    # 2. SHA-256 Calculation
    sha256 = calculate_sha256(file_content)

    # 3. Deduplication check within company and competence
    existing_duplicate = db.query(Document).filter(
        Document.company_id == company_id,
        Document.competence == competence,
        Document.file_hash_sha256 == sha256
    ).first()

    if existing_duplicate:
        # Existing document already recorded
        existing_receipt = db.query(DocumentReceipt).filter(
            DocumentReceipt.document_id == existing_duplicate.id
        ).first()
        return existing_duplicate, existing_receipt, True

    # 4. Versioning check: same name in same folder/department
    previous_version_doc = db.query(Document).filter(
        Document.company_id == company_id,
        Document.competence == competence,
        Document.department == department,
        Document.file_name == file_name,
        Document.is_latest == True
    ).first()

    version_number = 1
    if previous_version_doc:
        previous_version_doc.is_latest = False
        version_number = previous_version_doc.version + 1

    # Store immutable content by hash, never by an untrusted client filename.
    from pathlib import Path
    from supreme_common.auth_context import current_context, tenant_path
    root = tenant_path(settings.STORAGE_DIR) if current_context.get() else Path(settings.STORAGE_DIR) / company_id
    root.mkdir(parents=True, exist_ok=True)
    target = root / sha256
    if not target.exists():
        temporary = root / (uuid.uuid4().hex + '.tmp')
        temporary.write_bytes(file_content)
        temporary.replace(target)
    storage_path = str(target)

    doc = Document(
        company_id=company_id,
        competence=competence,
        department=department,
        file_name=file_name,
        storage_path=storage_path,
        mime_type=mimetypes.guess_type(file_name)[0] or 'application/octet-stream',
        file_size_bytes=len(file_content),
        file_hash_sha256=sha256,
        version=version_number,
        is_latest=True,
        uploaded_by=uploaded_by,
        ingestion_source=ingestion_source,
        status="validated",
        created_at=datetime.now(timezone.utc)
    )
    db.add(doc)
    db.flush()

    # 6. Generate Official Digital Receipt (DoD)
    receipt_code = f"REC-{competence.replace('-', '')}-{uuid.uuid4().hex[:8].upper()}"
    receipt = DocumentReceipt(
        document_id=doc.id,
        receipt_code=receipt_code,
        file_hash_sha256=sha256,
        file_name=file_name,
        file_size_bytes=len(file_content),
        uploaded_by=uploaded_by,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp_utc=datetime.now(timezone.utc)
    )
    db.add(receipt)

    # 7. Update checklist items if matching department
    checklist = db.query(DocumentChecklist).filter(
        DocumentChecklist.company_id == company_id,
        DocumentChecklist.competence == competence
    ).first()
    if checklist:
        items = db.query(DocumentChecklistItem).filter(
            DocumentChecklistItem.checklist_id == checklist.id
        ).all()
        # Find first unfulfilled item in this department
        for item in items:
            if not item.is_fulfilled and item.department == department:
                item.is_fulfilled = True
                item.fulfilled_by_document_id = doc.id
                break
        # Recalculate percentage
        total = len(items)
        fulfilled = sum(1 for it in items if it.is_fulfilled)
        checklist.completion_percentage = int((fulfilled / total) * 100) if total > 0 else 100

    db.commit()
    db.refresh(doc)
    db.refresh(receipt)
    return doc, receipt, False


def get_or_create_monthly_checklist(
    db: Session,
    company_id: str,
    competence: str
) -> DocumentChecklist:
    """Fetches or initializes the monthly document checklist with department items."""
    checklist = db.query(DocumentChecklist).filter(
        DocumentChecklist.company_id == company_id,
        DocumentChecklist.competence == competence
    ).first()

    if not checklist:
        checklist = DocumentChecklist(
            company_id=company_id,
            competence=competence,
            title=f"Checklist Mensal de Documentos - Competência {competence}",
            completion_percentage=0
        )
        db.add(checklist)
        db.flush()

        standard_items = [
            ("Extratos Bancários OFX de Todas as Contas", "financeiro"),
            ("Comprovantes de Pagamentos e Despesas", "financeiro"),
            ("Notas Fiscais de Entrada e Saída (XML)", "fiscal"),
            ("Notas Fiscais de Serviços Tomados e Prestados (XML/PDF)", "fiscal"),
            ("Espelhos de Ponto e Atestados Médicos", "rh"),
        ]
        for title, dept in standard_items:
            db.add(DocumentChecklistItem(
                checklist_id=checklist.id,
                title=title,
                department=dept,
                is_required=True,
                is_fulfilled=False
            ))
        db.commit()
        db.refresh(checklist)

    return checklist
