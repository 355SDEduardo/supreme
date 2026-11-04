"""SQLAlchemy Models for Feature 01: Central de Obrigações, Tarefas e Prazos."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, Date, Boolean, Enum, ForeignKey, JSON
)
from portalcontabilidades.core.database import Base


class TaxObligation(Base):
    """Master catalog of tax and regulatory obligations."""
    __tablename__ = "tax_obligations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, nullable=False)  # DAS, DCTFWEB, REINF, ESOCIAL, FGTS_DIGITAL
    name = Column(String(255), nullable=False)
    sphere = Column(Enum("federal", "estadual", "municipal", "trabalhista", name="sphere_enum"), default="federal")
    periodicity = Column(Enum("mensal", "trimestral", "anual", "eventual", name="periodicity_enum"), default="mensal")
    due_day_rule = Column(String(50), default="15")  # e.g., '15_anticipate', '20_postpone', '20_anticipate'
    applicable_regimes = Column(JSON, nullable=True)  # ['simples_nacional', 'lucro_presumido', 'lucro_real']
    has_receipt_required_default = Column(Boolean, default=True)


class CompanyObligation(Base):
    """Obligations activated for a specific client company."""
    __tablename__ = "company_obligations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    obligation_id = Column(String(36), ForeignKey("tax_obligations.id"), nullable=False)
    is_active = Column(Boolean, default=True)


class Task(Base):
    """Instantiated task for a specific company, obligation, and competence."""
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id = Column(String(36), nullable=False, index=True)
    obligation_code = Column(String(50), nullable=True, index=True)
    competence = Column(String(7), nullable=False, index=True)  # '2026-09'
    title = Column(String(255), nullable=False)
    statutory_due_date = Column(Date, nullable=False)  # Fisco legal deadline
    internal_deadline = Column(Date, nullable=False)   # Internal target
    status = Column(
        Enum("todo", "in_progress", "waiting_client", "in_review", "completed", "overdue", name="task_status_enum"),
        default="todo",
        nullable=False,
        index=True
    )
    assigned_to = Column(String(36), nullable=True, index=True) # Analyst
    reviewed_by = Column(String(36), nullable=True)            # Supervisor
    has_receipt_required = Column(Boolean, default=True)
    receipt_file_id = Column(String(36), nullable=True)
    receipt_file_hash = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaskDependency(Base):
    """Enforces execution order (DAG). `blocked_task_id` cannot be completed while `prerequisite_task_id` is open."""
    __tablename__ = "task_dependencies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    blocked_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    prerequisite_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)


class TaskAuditLog(Base):
    """Immutable log of task state transitions and attachments."""
    __tablename__ = "task_audit_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    user_id = Column(String(36), nullable=True)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False)  # 'status_changed', 'receipt_attached', 'deadline_extended'
    ip_address = Column(String(45), nullable=True)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
