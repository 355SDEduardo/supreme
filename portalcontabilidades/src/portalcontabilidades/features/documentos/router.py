"""FastAPI Router for Feature 02: Gestão Inteligente de Documentos."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from portalcontabilidades.core.database import get_db

from .schemas import (
    DocumentResponse, DocumentReceiptResponse,
    DocumentChecklistResponse, DocumentChecklistItemResponse, RequestChecklistInput
)
from .models import Document, DocumentReceipt, DocumentChecklist, DocumentChecklistItem
from .service import (
    process_document_upload, get_or_create_monthly_checklist
)

router = APIRouter(prefix="/documents", tags=["Feature 02: Gestão Inteligente de Documentos"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    company_id: str = Form(...),
    competence: str = Form(...),
    department: str = Form("fiscal"),
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Ingest document with validation, magic numbers inspection, SHA-256 deduplication, versioning, and receipt."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    ip = request.client.host if (request and request.client) else "127.0.0.1"
    user_agent = request.headers.get("user-agent") if request else None

    doc, receipt, is_dup = process_document_upload(
        db=db,
        company_id=company_id,
        competence=competence,
        department=department,
        file_name=file.filename,
        file_content=content,
        ip_address=ip,
        user_agent=user_agent
    )

    return DocumentResponse(
        id=doc.id,
        company_id=doc.company_id,
        competence=doc.competence,
        department=doc.department,
        file_name=doc.file_name,
        file_size_bytes=doc.file_size_bytes,
        file_hash_sha256=doc.file_hash_sha256,
        version=doc.version,
        is_latest=doc.is_latest,
        status=doc.status,
        ocr_status=doc.ocr_status,
        receipt_code=receipt.receipt_code if receipt else None,
        created_at=doc.created_at
    )


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    company_id: Optional[str] = None,
    competence: Optional[str] = None,
    department: Optional[str] = None,
    status: Optional[str] = None,
    only_latest: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List documents with faceted filters by company, competence, and department."""
    query = db.query(Document)
    if company_id:
        query = query.filter(Document.company_id == company_id)
    if competence:
        query = query.filter(Document.competence == competence)
    if department:
        query = query.filter(Document.department == department)
    if status:
        query = query.filter(Document.status == status)
    if only_latest:
        query = query.filter(Document.is_latest == True)

    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    results = []
    for d in docs:
        receipt = db.query(DocumentReceipt).filter(DocumentReceipt.document_id == d.id).first()
        results.append(
            DocumentResponse(
                id=d.id,
                company_id=d.company_id,
                competence=d.competence,
                department=d.department,
                file_name=d.file_name,
                file_size_bytes=d.file_size_bytes,
                file_hash_sha256=d.file_hash_sha256,
                version=d.version,
                is_latest=d.is_latest,
                status=d.status,
                ocr_status=d.ocr_status,
                receipt_code=receipt.receipt_code if receipt else None,
                created_at=d.created_at
            )
        )
    return results


@router.get("/{document_id}/receipt", response_model=DocumentReceiptResponse)
def get_document_receipt(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Retrieve official digital proof of delivery for audit trail and compliance."""
    receipt = db.query(DocumentReceipt).filter(DocumentReceipt.document_id == document_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Protocolo de entrega não encontrado.")
    return DocumentReceiptResponse(
        receipt_code=receipt.receipt_code,
        document_id=receipt.document_id,
        file_name=receipt.file_name,
        file_hash_sha256=receipt.file_hash_sha256,
        file_size_bytes=receipt.file_size_bytes,
        uploaded_by=receipt.uploaded_by,
        ip_address=receipt.ip_address,
        user_agent=receipt.user_agent,
        timestamp_utc=receipt.timestamp_utc
    )


@router.get("/{document_id}/preview")
def preview_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Secure preview stream or text representation."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return PlainTextResponse(f"Pré-visualização do documento: {doc.file_name} (Hash: {doc.file_hash_sha256})")


@router.post("/checklists/request", response_model=DocumentChecklistResponse)
def request_missing_documents(
    payload: RequestChecklistInput,
    db: Session = Depends(get_db)
):
    """Initialize or dispatch checklist of missing documents for the month."""
    checklist = get_or_create_monthly_checklist(db, payload.company_id, payload.competence)
    items = db.query(DocumentChecklistItem).filter(DocumentChecklistItem.checklist_id == checklist.id).all()
    return DocumentChecklistResponse(
        id=checklist.id,
        company_id=checklist.company_id,
        competence=checklist.competence,
        title=checklist.title,
        completion_percentage=checklist.completion_percentage,
        items=[
            DocumentChecklistItemResponse(
                id=it.id,
                title=it.title,
                department=it.department,
                is_required=it.is_required,
                is_fulfilled=it.is_fulfilled,
                fulfilled_by_document_id=it.fulfilled_by_document_id
            )
            for it in items
        ]
    )
