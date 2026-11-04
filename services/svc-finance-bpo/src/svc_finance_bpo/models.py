"""SQLAlchemy Models for Feature 04: Contas a Pagar e Receber."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Date, Numeric, Enum, ForeignKey, Integer, JSON
)
from svc_finance_bpo.database import Base


class PayableReceivableBill(Base):
    __tablename__ = "payable_receivable_bills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    type = Column(Enum("payable", "receivable", name="bill_type_enum"), nullable=False, index=True)
    counterparty_name = Column(String(255), nullable=False)  # Fornecedor ou Cliente
    counterparty_tax_id = Column(String(18), nullable=True)  # CNPJ ou CPF
    category_id = Column(String(36), nullable=True)          # Plano de contas
    cost_center_id = Column(String(36), nullable=True)
    document_number = Column(String(50), nullable=True)      # NF ou Fatura
    original_amount = Column(Numeric(15, 2), nullable=False)
    discount_amount = Column(Numeric(15, 2), default=0.00)
    interest_penalty_amount = Column(Numeric(15, 2), default=0.00)
    final_amount = Column(Numeric(15, 2), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    payment_date = Column(Date, nullable=True)
    payment_method = Column(
        Enum("boleto", "pix", "ted", "card", "cash", "other", name="payment_method_enum"),
        default="boleto",
        nullable=False
    )
    barcode_line = Column(String(60), nullable=True)
    pix_key = Column(String(100), nullable=True)
    pix_emv_payload = Column(Text, nullable=True)
    status = Column(
        Enum("draft", "pending_approval", "approved", "scheduled", "paid", "canceled", "rejected", name="bill_status_enum"),
        default="draft",
        nullable=False,
        index=True
    )
    created_by_user_id = Column(String(36), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    required_approvals = Column(Integer, default=1)
    current_approvals = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BillApproval(Base):
    __tablename__ = "bill_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bill_id = Column(String(36), ForeignKey("payable_receivable_bills.id"), nullable=False, index=True)
    approver_user_id = Column(String(36), nullable=False)
    level = Column(Integer, default=1)
    status = Column(Enum("pending", "approved", "rejected", name="approval_status_enum"), default="pending")
    comments = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=False)
    approved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class BillingLog(Base):
    __tablename__ = "billing_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bill_id = Column(String(36), ForeignKey("payable_receivable_bills.id"), nullable=False, index=True)
    channel = Column(String(20), default="whatsapp")  # whatsapp, email
    message_type = Column(String(50), nullable=False) # reminder_d_minus_3, reminder_due_day, overdue_notice
    recipient = Column(String(100), nullable=False)
    status = Column(String(20), default="sent")
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
