"""SQLAlchemy Models for Feature 03: Conciliação Bancária Automática."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Date, Numeric, Enum, ForeignKey, Boolean, JSON
)
from portalcontabilidades.core.database import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    bank_code = Column(String(10), nullable=False)   # 001, 237, 341, 077, 260
    bank_name = Column(String(100), nullable=False)  # Itaú, Bradesco, Inter
    agency_number = Column(String(20), nullable=False)
    account_number = Column(String(30), nullable=False)
    current_balance = Column(Numeric(15, 2), default=0.00, nullable=False)
    open_finance_consent_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)


class BankStatement(Base):
    __tablename__ = "bank_statements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    import_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    opening_balance = Column(Numeric(15, 2), nullable=False)
    closing_balance = Column(Numeric(15, 2), nullable=False)
    total_credits = Column(Numeric(15, 2), default=0.00)
    total_debits = Column(Numeric(15, 2), default=0.00)
    status = Column(
        Enum("imported", "partially_reconciled", "fully_reconciled", "locked", name="stmt_status_enum"),
        default="imported",
        nullable=False
    )


class BankTransaction(Base):
    """Bank statement entry extracted from OFX/CSV/Open Finance."""
    __tablename__ = "bank_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    statement_id = Column(String(36), ForeignKey("bank_statements.id"), nullable=True, index=True)
    fitid = Column(String(100), unique=True, nullable=False, index=True) # Unique bank ID for deduplication
    transaction_date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False) # Positive = credit/inflow, Negative = debit/outflow
    memo = Column(Text, nullable=False)
    document_number = Column(String(50), nullable=True)
    status = Column(
        Enum("pending", "matched", "divergent", "ignored", name="trx_status_enum"),
        default="pending",
        nullable=False,
        index=True
    )
    reconciliation_id = Column(String(36), ForeignKey("reconciliations.id"), nullable=True)


class Reconciliation(Base):
    """Confirmed matching between bank transactions and books/bills."""
    __tablename__ = "reconciliations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    bank_account_id = Column(String(36), ForeignKey("bank_accounts.id"), nullable=False)
    match_type = Column(
        Enum("exact_1_1", "grouped_1_n", "grouped_n_1", "manual_adjustment", name="match_type_enum"),
        default="exact_1_1",
        nullable=False
    )
    difference_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    reconciled_by = Column(String(36), nullable=True)
    reconciled_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ReconciliationItem(Base):
    """Join linking bank transactions to reconciled payable/receivable bill IDs."""
    __tablename__ = "reconciliation_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reconciliation_id = Column(String(36), ForeignKey("reconciliations.id"), nullable=False, index=True)
    bank_transaction_id = Column(String(36), ForeignKey("bank_transactions.id"), nullable=True)
    bill_id = Column(String(36), nullable=True, index=True) # Points to payable_receivable_bills.id
    allocated_amount = Column(Numeric(15, 2), nullable=False)
