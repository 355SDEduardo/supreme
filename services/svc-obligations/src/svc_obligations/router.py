"""FastAPI Router for Feature 01: Central de Obrigações, Tarefas e Prazos."""

from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from svc_obligations.database import get_db

from .schemas import (
    TaskResponse, TaskStatusUpdate, TaskAttachmentInput,
    CompetenceBatchGenerateInput, CompetenceBatchGenerateResult,
    TaxObligationResponse, WorkloadSummaryItem
)
from .models import Task, TaxObligation
from .service import (
    generate_tasks_for_competence, update_task_status,
    attach_task_receipt, calculate_task_risk
)

router = APIRouter(tags=["Feature 01: Central de Obrigações, Tarefas e Prazos"])


@router.get("/companies/{company_id}/obligations", response_model=List[TaxObligationResponse])
def get_company_obligations(
    company_id: str,
    db: Session = Depends(get_db)
):
    """Retrieve catalog of obligations active for a company."""
    obligations = db.query(TaxObligation).all()
    return obligations


@router.post("/tasks/generate-competence", response_model=CompetenceBatchGenerateResult)
def generate_competence_batch(
    payload: CompetenceBatchGenerateInput,
    db: Session = Depends(get_db)
):
    """Batch generate recurring tasks and regulatory due dates for all client companies."""
    # Build company_id -> tax_regime map (mocked or retrieved from DB)
    company_regimes = {comp_id: "simples_nacional" for comp_id in (payload.company_ids or ["comp-default-01"])}
    return generate_tasks_for_competence(db=db, input_data=payload, company_regimes=company_regimes)


@router.get("/tasks", response_model=List[TaskResponse])
def list_tasks(
    company_id: Optional[str] = None,
    competence: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List tasks with filters, ordering by statutory due date, and SLA risk levels."""
    query = db.query(Task)
    if company_id:
        query = query.filter(Task.company_id == company_id)
    if competence:
        query = query.filter(Task.competence == competence)
    if status:
        query = query.filter(Task.status == status)
    if assigned_to:
        query = query.filter(Task.assigned_to == assigned_to)

    tasks = query.order_by(Task.statutory_due_date.asc()).offset(offset).limit(limit).all()
    results = []
    for t in tasks:
        risk, days_left = calculate_task_risk(t.statutory_due_date, t.status)
        results.append(
            TaskResponse(
                id=t.id,
                company_id=t.company_id,
                obligation_code=t.obligation_code,
                competence=t.competence,
                title=t.title,
                statutory_due_date=t.statutory_due_date,
                internal_deadline=t.internal_deadline,
                status=t.status,
                assigned_to=t.assigned_to,
                reviewed_by=t.reviewed_by,
                has_receipt_required=t.has_receipt_required,
                receipt_file_id=t.receipt_file_id,
                receipt_file_hash=t.receipt_file_hash,
                risk_level=risk,
                days_to_due=days_left,
                created_at=t.created_at
            )
        )
    return results


@router.patch("/tasks/{task_id}/status", response_model=TaskResponse)
def change_task_status(
    task_id: str,
    payload: TaskStatusUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Transition task status, enforcing dependency completion and mandatory receipt attachments."""
    ip = request.client.host if request.client else "127.0.0.1"
    return update_task_status(db=db, task_id=task_id, update_data=payload, ip_address=ip)


@router.post("/tasks/{task_id}/attachments")
def upload_task_attachment(
    task_id: str,
    payload: TaskAttachmentInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Attach official proof or receipt of transmission to a task."""
    ip = request.client.host if request.client else "127.0.0.1"
    task = attach_task_receipt(
        db=db,
        task_id=task_id,
        file_id=payload.file_id,
        file_hash=payload.file_hash,
        user_id=payload.user_id,
        ip_address=ip
    )
    return {"status": "attached", "task_id": task.id, "receipt_file_id": task.receipt_file_id}


@router.get("/tasks/workload", response_model=List[WorkloadSummaryItem])
def get_workload_report(
    competence: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Workload distribution across analysts and team capacity."""
    query = db.query(Task)
    if competence:
        query = query.filter(Task.competence == competence)
    tasks = query.all()

    workload_map: Dict[str, Dict[str, int]] = {}
    for t in tasks:
        analyst = t.assigned_to or "unassigned"
        stats = workload_map.setdefault(
            analyst,
            {"total": 0, "completed": 0, "pending": 0, "overdue": 0, "critical": 0}
        )
        stats["total"] += 1
        risk, _ = calculate_task_risk(t.statutory_due_date, t.status)
        if t.status == "completed":
            stats["completed"] += 1
        else:
            stats["pending"] += 1
            if risk == "overdue":
                stats["overdue"] += 1
            elif risk == "red_critical":
                stats["critical"] += 1

    return [
        WorkloadSummaryItem(
            analyst_user_id=analyst,
            total_tasks=data["total"],
            completed_tasks=data["completed"],
            pending_tasks=data["pending"],
            overdue_tasks=data["overdue"],
            critical_risk_tasks=data["critical"]
        )
        for analyst, data in workload_map.items()
    ]
