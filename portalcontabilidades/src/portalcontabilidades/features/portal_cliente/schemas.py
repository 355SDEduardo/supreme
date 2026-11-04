"""Pydantic schemas for Feature 06: Portal do Cliente e Comunicação."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    company_id: str
    category: str = Field(..., description="admission, termination, vacation, fiscal, accounting, bpo_finance, other")
    title: str = Field(..., min_length=3, max_length=255)
    priority: str = "medium"  # low, medium, high, urgent
    user_id: str
    structured_data: Optional[Dict[str, Any]] = None


class TicketResponse(BaseModel):
    id: str
    company_id: str
    category: str
    title: str
    status: str
    priority: str
    sla_hours: int
    sla_due_at: datetime
    assigned_agent_id: Optional[str]
    created_by_user_id: str
    structured_data: Optional[Dict[str, Any]]
    created_at: datetime


class TicketMessageCreate(BaseModel):
    sender_id: str
    sender_type: str = "client_user"  # client_user, staff_agent, system_bot
    message_body: str = Field(..., min_length=1)
    channel: str = "portal"  # portal, whatsapp, email
    attachments: Optional[List[Dict[str, Any]]] = None


class TicketMessageResponse(BaseModel):
    id: str
    ticket_id: str
    sender_id: Optional[str]
    sender_type: str
    message_body: str
    channel: str
    created_at: datetime


class AvailableGuideItem(BaseModel):
    document_id: str
    company_id: str
    title: str
    competence: str
    due_date: str
    barcode_line: Optional[str] = None
    pix_key: Optional[str] = None
    download_url: str
    viewed_by_client: bool
    viewed_at: Optional[datetime] = None


class GuideReceiptConfirmInput(BaseModel):
    document_id: str
    company_id: str
    user_id: str
    action_type: str = "viewed_and_confirmed"  # viewed_and_confirmed, downloaded, copied_pix


class GuideReceiptConfirmResponse(BaseModel):
    receipt_id: str
    document_id: str
    confirmed_at: datetime
    ip_address: str
    message: str


class WhatsAppWebhookInput(BaseModel):
    sender_phone: str
    message_body: str
    company_id: Optional[str] = None
    ticket_id: Optional[str] = None
