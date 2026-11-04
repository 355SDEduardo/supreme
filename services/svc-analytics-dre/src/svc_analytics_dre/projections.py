"""Private CQRS projections populated from durable domain events."""
from sqlalchemy import Column, String, Numeric, Date
from .database import Base

class BillProjection(Base):
    __tablename__ = 'bill_projections'
    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), nullable=False, index=True)
    type = Column(String(20), nullable=False)
    category = Column(String(100), nullable=True)
    status = Column(String(30), nullable=False)
    amount = Column(Numeric(18,2), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    payment_date = Column(Date, nullable=True)

class AccountProjection(Base):
    __tablename__ = 'account_projections'
    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), nullable=False, index=True)
    balance = Column(Numeric(18,2), nullable=False)
    as_of = Column(Date, nullable=False)

class ConsumedEvent(Base):
    __tablename__ = 'consumed_events'
    id = Column(String(100), primary_key=True)
