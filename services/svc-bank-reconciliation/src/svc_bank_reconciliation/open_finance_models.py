"""Additive, service-owned tables. Existing OFX/reconciliation records are untouched."""

from __future__ import annotations

from sqlalchemy import Column, Date, ForeignKey, Integer, String, Text

from .database import Base


class OpenFinanceConnection(Base):
    __tablename__ = "open_finance_connections"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False)
    client_user_id = Column(String(64), nullable=False, unique=True)
    connector_id = Column(Integer, nullable=False)
    connector_name = Column(String(200), nullable=False)
    item_id = Column(String(36), nullable=True, unique=True)
    expires_at = Column(String(40), nullable=False)
    disconnected_at = Column(String(40), nullable=True)
    synced_at = Column(String(40), nullable=True)
    source_updated_at = Column(String(40), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    # Optimistic concurrency protects sync, completion and disconnect across workers.
    version = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class OpenFinanceAccount(Base):
    __tablename__ = "open_finance_accounts"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("open_finance_connections.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    number = Column(String(200), nullable=False)
    currency_code = Column(String(3), nullable=False)
    # Canonical decimal text avoids SQLite's binary-float conversion of NUMERIC.
    balance = Column(String(64), nullable=False)


class OpenFinanceTransaction(Base):
    __tablename__ = "open_finance_transactions"

    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("open_finance_accounts.id"), nullable=False, index=True)
    transaction_date = Column(Date, nullable=False, index=True)
    data = Column(Text, nullable=False)  # Validated projection, Decimal values encoded as strings.
