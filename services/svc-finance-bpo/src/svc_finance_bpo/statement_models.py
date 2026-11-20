from __future__ import annotations

from sqlalchemy import Column, Date, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint

from .database import Base


class StatementImport(Base):
    __tablename__ = 'bpo_statement_imports'
    __table_args__ = (UniqueConstraint('organization_id', 'company_id', 'fingerprint'),)
    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    account_key = Column(String(100), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False)
    created_by = Column(String(100), nullable=False)
    created_at = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default='preview')
    payload = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class StatementSource(Base):
    __tablename__ = 'bpo_statement_sources'
    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    import_id = Column(String(36), ForeignKey('bpo_statement_imports.id'), nullable=False, index=True)
    source_id = Column(String(32), nullable=False)
    filename = Column(String(200), nullable=False)
    content = Column(LargeBinary, nullable=False)


class StatementMovement(Base):
    __tablename__ = 'bpo_statement_movements'
    __table_args__ = (UniqueConstraint('organization_id', 'company_id', 'account_key', 'dedupe_key'),)
    id = Column(String(36), primary_key=True)
    organization_id = Column(String(100), nullable=False, index=True)
    company_id = Column(String(100), nullable=False, index=True)
    account_key = Column(String(100), nullable=False, index=True)
    import_id = Column(String(36), ForeignKey('bpo_statement_imports.id'), nullable=False, index=True)
    group_id = Column(String(32), nullable=False)
    dedupe_key = Column(String(64), nullable=False)
    date = Column(Date, nullable=False, index=True)
    amount = Column(String(32), nullable=False)
    type = Column(String(10), nullable=False)
    description = Column(Text, nullable=False)
    provenance = Column(Text, nullable=False)
