"""Service logic for Feature 01: Central de Obrigações, Tarefas e Prazos."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import Task, TaskDependency, TaskAuditLog, TaxObligation
from .schemas import (
    CompetenceBatchGenerateInput, CompetenceBatchGenerateResult,
    TaskStatusUpdate, TaskResponse, WorkloadSummaryItem
)
from .calendar_engine import calculate_tax_due_date

DEFAULT_OBLIGATIONS_BY_REGIME = {
    "simples_nacional": [
        ("DAS", "Apuração e Emissão da Guia DAS (PGDAS-D)", True),
        ("ESOCIAL", "Fechamento da Folha eSocial (S-1299)", True),
        ("FGTS_DIGITAL", "Emissão e Transmissão do FGTS Digital", True),
    ],
    "lucro_presumido": [
        ("ESOCIAL", "Fechamento da Folha eSocial (S-1299)", True),
        ("REINF", "Transmissão da EFD-Reinf (Série R-4000)", True),
        ("DCTFWEB", "Transmissão da DCTFWeb e Geração de DARF", True),
        ("FGTS_DIGITAL", "Emissão e Transmissão do FGTS Digital", True),
    ],
    "lucro_real": [
        ("ESOCIAL", "Fechamento da Folha eSocial (S-1299)", True),
        ("REINF", "Transmissão da EFD-Reinf (Série R-4000)", True),
        ("DCTFWEB", "Transmissão da DCTFWeb e Geração de DARF", True),
        ("FGTS_DIGITAL", "Emissão e Transmissão do FGTS Digital", True),
    ],
    "mei": [
        ("DAS", "Guia DAS-MEI da Competência", False),
    ]
}


def calculate_task_risk(statutory_due_date: date, status: str) -> Tuple[str, int]:
    """Calculates SLA risk level: 'green', 'yellow_alert' (72h-24h), 'red_critical' (<24h), 'overdue'."""
    today = date.today()
    days_left = (statutory_due_date - today).days

    if status == "completed":
        return "green", days_left
    if days_left < 0:
        return "overdue", days_left
    if days_left <= 1:
        return "red_critical", days_left
    if days_left <= 3:
        return "yellow_alert", days_left
    return "green", days_left


def generate_tasks_for_competence(
    db: Session,
    input_data: CompetenceBatchGenerateInput,
    company_regimes: Dict[str, str]  # company_id -> tax_regime
) -> CompetenceBatchGenerateResult:
    """Generates competence tasks in batch for given companies with statutory deadlines and dependency chains."""
    companies_processed = 0
    tasks_generated = 0
    errors: List[Dict[str, str]] = []

    for comp_id, regime in company_regimes.items():
        try:
            obligations = DEFAULT_OBLIGATIONS_BY_REGIME.get(regime, DEFAULT_OBLIGATIONS_BY_REGIME["simples_nacional"])
            created_tasks: Dict[str, Task] = {}

            for code, title, receipt_req in obligations:
                # Check for existing task to prevent duplicate generation
                existing = db.query(Task).filter(
                    Task.company_id == comp_id,
                    Task.competence == input_data.competence,
                    Task.obligation_code == code
                ).first()

                if not existing:
                    stat_due = calculate_tax_due_date(input_data.competence, code)
                    internal_due = stat_due - timedelta(days=2)  # Internal SLA: 2 days prior to fiscal deadline

                    task = Task(
                        company_id=comp_id,
                        obligation_code=code,
                        competence=input_data.competence,
                        title=title,
                        statutory_due_date=stat_due,
                        internal_deadline=internal_due,
                        status="todo",
                        has_receipt_required=receipt_req,
                    )
                    db.add(task)
                    db.flush()
                    created_tasks[code] = task
                    tasks_generated += 1
                else:
                    created_tasks[code] = existing

            # Setup dependencies: DCTFWeb depends on eSocial and Reinf
            if "DCTFWEB" in created_tasks:
                dctf_task = created_tasks["DCTFWEB"]
                if "ESOCIAL" in created_tasks:
                    esocial_task = created_tasks["ESOCIAL"]
                    dep_exists = db.query(TaskDependency).filter(
                        TaskDependency.blocked_task_id == dctf_task.id,
                        TaskDependency.prerequisite_task_id == esocial_task.id
                    ).first()
                    if not dep_exists:
                        db.add(TaskDependency(blocked_task_id=dctf_task.id, prerequisite_task_id=esocial_task.id))

                if "REINF" in created_tasks:
                    reinf_task = created_tasks["REINF"]
                    dep_exists = db.query(TaskDependency).filter(
                        TaskDependency.blocked_task_id == dctf_task.id,
                        TaskDependency.prerequisite_task_id == reinf_task.id
                    ).first()
                    if not dep_exists:
                        db.add(TaskDependency(blocked_task_id=dctf_task.id, prerequisite_task_id=reinf_task.id))

            companies_processed += 1
        except Exception as e:
            errors.append({"company_id": comp_id, "error": str(e)})

    db.commit()
    return CompetenceBatchGenerateResult(
        competence=input_data.competence,
        companies_processed=companies_processed,
        tasks_generated=tasks_generated,
        errors=errors
    )


def update_task_status(
    db: Session,
    task_id: str,
    update_data: TaskStatusUpdate,
    ip_address: Optional[str] = None
) -> TaskResponse:
    """Updates task status, validating DAG dependencies and receipt requirement before completion."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    new_status = update_data.new_status

    if new_status == "completed":
        # 1. Receipt validation
        if task.has_receipt_required and not task.receipt_file_id:
            raise HTTPException(
                status_code=400,
                detail="Não é possível concluir a tarefa: anexo do recibo/protocolo de entrega é obrigatório."
            )

        # 2. Dependency DAG check
        prereq_deps = db.query(TaskDependency).filter(TaskDependency.blocked_task_id == task.id).all()
        for dep in prereq_deps:
            prereq = db.query(Task).filter(Task.id == dep.prerequisite_task_id).first()
            if prereq and prereq.status != "completed":
                raise HTTPException(
                    status_code=400,
                    detail=f"Tarefa bloqueada pela dependência '{prereq.title}' que ainda está com status '{prereq.status}'."
                )

    old_status = task.status
    task.status = new_status
    task.updated_at = datetime.now(timezone.utc)

    # Immutable Audit Log
    log = TaskAuditLog(
        task_id=task.id,
        user_id=update_data.user_id,
        previous_status=old_status,
        new_status=new_status,
        action="status_changed",
        ip_address=ip_address,
        details={"notes": update_data.notes}
    )
    db.add(log)
    db.commit()
    db.refresh(task)

    risk, days_left = calculate_task_risk(task.statutory_due_date, task.status)
    return TaskResponse(
        id=task.id,
        company_id=task.company_id,
        obligation_code=task.obligation_code,
        competence=task.competence,
        title=task.title,
        statutory_due_date=task.statutory_due_date,
        internal_deadline=task.internal_deadline,
        status=task.status,
        assigned_to=task.assigned_to,
        reviewed_by=task.reviewed_by,
        has_receipt_required=task.has_receipt_required,
        receipt_file_id=task.receipt_file_id,
        receipt_file_hash=task.receipt_file_hash,
        risk_level=risk,
        days_to_due=days_left,
        created_at=task.created_at
    )


def attach_task_receipt(
    db: Session,
    task_id: str,
    file_id: str,
    file_hash: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Task:
    """Attaches an official proof/receipt file with SHA-256 hash to a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    task.receipt_file_id = file_id
    task.receipt_file_hash = file_hash

    log = TaskAuditLog(
        task_id=task.id,
        user_id=user_id,
        previous_status=task.status,
        new_status=task.status,
        action="receipt_attached",
        ip_address=ip_address,
        details={"file_id": file_id, "file_hash": file_hash}
    )
    db.add(log)
    db.commit()
    db.refresh(task)
    return task
