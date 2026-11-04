"""SQLAlchemy Models for Feature 07: Fluxo de Caixa, DRE e Dashboards."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Date, Numeric, Enum, ForeignKey, Boolean, JSON
)
from svc_analytics_dre.database import Base


class ChartOfAccounts(Base):
    """Chart of accounts hierarchy (Plano de Contas)."""
    __tablename__ = "chart_of_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    code = Column(String(50), nullable=False)   # e.g., '1.1.01', '3.1.01'
    name = Column(String(255), nullable=False)
    account_type = Column(
        Enum("asset", "liability", "equity", "revenue", "cogs", "expense", "financial", name="account_type_enum"),
        nullable=False
    )
    nature = Column(Enum("debit", "credit", name="account_nature_enum"), nullable=False)
    is_synthetic = Column(Boolean, default=False)
    parent_id = Column(String(36), ForeignKey("chart_of_accounts.id"), nullable=True)


class CostCenter(Base):
    __tablename__ = "cost_centers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)


class FinancialSnapshot(Base):
    """Denormalized analytical table for sub-second DRE and Cash Flow performance."""
    __tablename__ = "financial_snapshots"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    competence = Column(String(7), nullable=False, index=True)  # '2026-09'
    view_type = Column(Enum("accrual_dre", "cash_flow", name="view_type_enum"), nullable=False, index=True)
    line_code = Column(String(50), nullable=False)
    line_description = Column(String(255), nullable=False)
    realized_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    projected_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
