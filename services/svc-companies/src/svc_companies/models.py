"""SQLAlchemy Models for Feature 09: Gestão Multiempresa."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Enum, ForeignKey, Boolean, Integer, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from svc_companies.database import Base


class Organization(Base):
    """Accounting firm or BPO service provider (Primary Tenant)."""
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    tax_id = Column(String(18), unique=True, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Company(Base):
    """Client companies serviced by the organization."""
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint('organization_id','tax_id'),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    corporate_name = Column(String(255), nullable=False)  # Razão Social
    trade_name = Column(String(255), nullable=True)       # Nome Fantasia
    tax_id = Column(String(18), nullable=False, index=True)  # CNPJ ou CPF
    tax_regime = Column(
        Enum("simples_nacional", "lucro_presumido", "lucro_real", "mei", "imune_isenta", name="tax_regime_enum"),
        nullable=False,
        default="simples_nacional"
    )
    state_tax_id = Column(String(30), nullable=True)     # Inscrição Estadual
    municipal_tax_id = Column(String(30), nullable=True) # Inscrição Municipal
    cnae_code = Column(String(10), nullable=True)
    status = Column(
        Enum("active", "onboarding", "suspended", "archived", name="company_status_enum"),
        default="active",
        nullable=False
    )
    parent_company_id = Column(String(36), ForeignKey("companies.id"), nullable=True) # Matriz / Filial
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    global_role = Column(
        Enum("super_admin", "supervisor", "analyst", "bpo_operator", "client_user", name="user_global_role_enum"),
        default="analyst",
        nullable=False
    )
    is_active = Column(Boolean, default=True)
    is_mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserCompanyRole(Base):
    """Specific role and permissions for a user within a company."""
    __tablename__ = "user_company_roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    role = Column(
        Enum("super_admin", "supervisor", "analyst", "bpo_operator", "client_admin", "client_restricted", name="company_role_enum"),
        default="analyst",
        nullable=False
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class CompanyTeamAssignment(Base):
    """Links between analysts and the client companies assigned to them."""
    __tablename__ = "company_team_assignments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False, index=True)
    analyst_user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    department = Column(String(50), default="geral")  # fiscal, contabil, dp, bpo
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
