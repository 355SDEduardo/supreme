"""Service logic for Feature 06: Portal do Cliente e Comunicação."""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import ClientTicket, TicketMessage, DocumentDownloadReceipt, NotificationLog
from .schemas import (
    TicketCreate, TicketMessageCreate, GuideReceiptConfirmInput,
    GuideReceiptConfirmResponse
)
from .ticket_validator import validate_structured_ticket_data, calculate_ticket_sla


def create_client_ticket(db: Session, data: TicketCreate) -> ClientTicket:
    """Creates structured support ticket, enforcing category field requirements (DoD)."""
    is_valid, err_msg = validate_structured_ticket_data(data.category, data.structured_data)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err_msg)

    sla_hours, sla_due_at = calculate_ticket_sla(data.priority)

    ticket = ClientTicket(
        company_id=data.company_id,
        category=data.category,
        title=data.title,
        status="open",
        priority=data.priority,
        sla_hours=sla_hours,
        sla_due_at=sla_due_at,
        created_by_user_id=data.user_id,
        structured_data=data.structured_data,
        created_at=datetime.now(timezone.utc)
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def add_ticket_message(
    db: Session,
    ticket_id: str,
    data: TicketMessageCreate
) -> TicketMessage:
    """Adds message to ticket communication thread."""
    ticket = db.query(ClientTicket).filter(ClientTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Chamado não encontrado.")

    msg = TicketMessage(
        ticket_id=ticket.id,
        sender_id=data.sender_id,
        sender_type=data.sender_type,
        message_body=data.message_body,
        channel=data.channel,
        attachments=data.attachments,
        created_at=datetime.now(timezone.utc)
    )
    db.add(msg)

    # If client answered, shift status to in_analysis
    if data.sender_type == "client_user" and ticket.status == "waiting_client":
        ticket.status = "in_analysis"

    db.commit()
    db.refresh(msg)
    return msg


def record_guide_receipt_confirmation(
    db: Session,
    data: GuideReceiptConfirmInput,
    ip_address: str = "127.0.0.1",
    user_agent: Optional[str] = None
) -> GuideReceiptConfirmResponse:
    """Records irrefutable delivery and confirmation proof with timestamp UTC and IP address (DoD)."""
    receipt = DocumentDownloadReceipt(
        document_id=data.document_id,
        company_id=data.company_id,
        user_id=data.user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        action_type=data.action_type,
        downloaded_at=datetime.now(timezone.utc)
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return GuideReceiptConfirmResponse(
        receipt_id=receipt.id,
        document_id=receipt.document_id,
        confirmed_at=receipt.downloaded_at,
        ip_address=receipt.ip_address,
        message="Ciência de recebimento registrada para fins de auditoria e comprovação jurídica."
    )
