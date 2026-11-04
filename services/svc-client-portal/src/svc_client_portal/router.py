"""FastAPI Router for Feature 06: Portal do Cliente e Comunicação."""

from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from svc_client_portal.database import get_db

from .schemas import (
    TicketCreate, TicketResponse, TicketMessageCreate, TicketMessageResponse,
    AvailableGuideItem, GuideReceiptConfirmInput, GuideReceiptConfirmResponse
)
from .models import ClientTicket, DocumentDownloadReceipt
from .service import (
    create_client_ticket, add_ticket_message, record_guide_receipt_confirmation
)

router = APIRouter(prefix="/portal", tags=["Feature 06: Portal do Cliente e Comunicação"])


@router.post("/tickets", response_model=TicketResponse)
def open_client_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db)
):
    """Open structured ticket enforcing category-specific mandatory schemas and SLAs."""
    ticket = create_client_ticket(db=db, data=payload)
    return ticket


@router.get("/tickets", response_model=List[TicketResponse])
def list_client_tickets(
    company_id: str = Query(...),
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List tickets belonging strictly to the authorized company."""
    query = db.query(ClientTicket).filter(ClientTicket.company_id == company_id)
    if status:
        query = query.filter(ClientTicket.status == status)
    if category:
        query = query.filter(ClientTicket.category == category)
    return query.order_by(ClientTicket.created_at.desc()).offset(offset).limit(limit).all()


@router.post("/tickets/{ticket_id}/messages", response_model=TicketMessageResponse)
def post_ticket_message(
    ticket_id: str,
    payload: TicketMessageCreate,
    db: Session = Depends(get_db)
):
    """Send message to ticket thread with multi-channel support."""
    return add_ticket_message(db=db, ticket_id=ticket_id, data=payload)


@router.get("/guides/available", response_model=List[AvailableGuideItem])
def list_available_guides(
    company_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """List pending and published tax guides and payslips with read/download confirmation status."""
    # Simulation: provides guides with confirmation tracking
    receipts = db.query(DocumentDownloadReceipt).filter(DocumentDownloadReceipt.company_id == company_id).all()
    viewed_doc_ids = {r.document_id: r.downloaded_at for r in receipts}

    guides = [
        AvailableGuideItem(
            document_id="doc-das-01",
            company_id=company_id,
            title="Guia DAS Simples Nacional - Competência 2026-09",
            competence="2026-09",
            due_date="2026-10-20",
            barcode_line="858900000010 234503282026 102000000000 123456789012",
            pix_key="11222333000181",
            download_url=f"/api/v1/documents/doc-das-01/preview",
            viewed_by_client="doc-das-01" in viewed_doc_ids,
            viewed_at=viewed_doc_ids.get("doc-das-01")
        )
    ]
    return guides


@router.post("/guides/{document_id}/confirm-receipt", response_model=GuideReceiptConfirmResponse)
def confirm_guide_receipt(
    document_id: str,
    payload: GuideReceiptConfirmInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Record receipt / view confirmation with IP, User, and Timestamp UTC."""
    payload.document_id = document_id
    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("user-agent")
    return record_guide_receipt_confirmation(db=db, data=payload, ip_address=ip, user_agent=ua)
