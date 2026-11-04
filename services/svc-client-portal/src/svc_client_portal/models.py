"""SQLAlchemy Models for Feature 06: Portal do Cliente e Comunicação."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Enum, ForeignKey, Integer, JSON
)
from svc_client_portal.database import Base


class ClientTicket(Base):
    __tablename__ = "client_tickets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    category = Column(
        Enum("admission", "termination", "vacation", "fiscal", "accounting", "bpo_finance", "other", name="ticket_category_enum"),
        nullable=False,
        index=True
    )
    title = Column(String(255), nullable=False)
    status = Column(
        Enum("open", "in_analysis", "waiting_client", "resolved", "closed", name="ticket_status_enum"),
        default="open",
        nullable=False,
        index=True
    )
    priority = Column(
        Enum("low", "medium", "high", "urgent", name="ticket_priority_enum"),
        default="medium",
        nullable=False
    )
    sla_hours = Column(Integer, default=24)
    sla_due_at = Column(DateTime, nullable=False)
    assigned_agent_id = Column(String(36), nullable=True)
    created_by_user_id = Column(String(36), nullable=False)
    structured_data = Column(JSON, nullable=True) # Validated fields specific to category
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String(36), ForeignKey("client_tickets.id"), nullable=False, index=True)
    sender_id = Column(String(36), nullable=True)
    sender_type = Column(
        Enum("client_user", "staff_agent", "system_bot", name="sender_type_enum"),
        default="client_user",
        nullable=False
    )
    message_body = Column(Text, nullable=False)
    channel = Column(
        Enum("portal", "whatsapp", "email", name="comm_channel_enum"),
        default="portal",
        nullable=False
    )
    attachments = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DocumentDownloadReceipt(Base):
    """Irrefutable legal defense proof of when a client downloaded or viewed a tax guide or payslip."""
    __tablename__ = "document_downloads_receipts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), nullable=False, index=True)
    company_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(36), nullable=False)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    action_type = Column(String(50), default="viewed_and_confirmed")  # 'downloaded', 'viewed', 'copied_pix'
    downloaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    recipient_contact = Column(String(100), nullable=False)
    channel = Column(Enum("email", "whatsapp", "push", "sms", name="notif_channel_enum"), default="whatsapp")
    template_name = Column(String(100), nullable=False)
    status = Column(Enum("sent", "delivered", "read", "failed", name="notif_status_enum"), default="sent")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
