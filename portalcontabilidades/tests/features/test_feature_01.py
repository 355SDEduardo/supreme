"""Unit and Integration Tests for Feature 01: Central de Obrigações, Tarefas e Prazos."""


import pytest
from datetime import date
from fastapi import HTTPException

from portalcontabilidades.features.obrigacoes.models import Task, TaskDependency, TaskAuditLog
from portalcontabilidades.features.obrigacoes.calendar_engine import (
    is_business_day, anticipate_to_business_day, postpone_to_business_day,
    calculate_tax_due_date, get_brazilian_national_holidays
)
from portalcontabilidades.features.obrigacoes.service import (
    generate_tasks_for_competence, update_task_status, attach_task_receipt, calculate_task_risk
)
from portalcontabilidades.features.obrigacoes.schemas import (
    CompetenceBatchGenerateInput, TaskStatusUpdate
)


def test_brazilian_calendar_and_holiday_shifts():
    """Validates holiday detection and weekend shifting rules."""
    holidays_2026 = get_brazilian_national_holidays(2026)
    assert date(2026, 1, 1) in holidays_2026   # New year
    assert date(2026, 9, 7) in holidays_2026   # Independência
    assert date(2026, 11, 20) in holidays_2026 # Consciência Negra
    assert date(2026, 12, 25) in holidays_2026 # Natal

    # Weekend checks (e.g. Saturday 2026-10-10 -> anticipation / postponement)
    saturday = date(2026, 10, 10)
    assert is_business_day(saturday) is False
    assert anticipate_to_business_day(saturday) == date(2026, 10, 9) # Friday
    # Since 2026-10-12 is holiday N. Sra Aparecida, postpone_to_business_day skips to Tuesday 10/13!
    assert postpone_to_business_day(saturday) == date(2026, 10, 13)


def test_tax_statutory_due_dates():
    """Validates statutory rules:
    - DAS: 20th of subsequent month, postponed if weekend/holiday.
    - DCTFWeb, eSocial, Reinf: 15th of subsequent month, anticipated if weekend/holiday.
    """
    # For competence 2026-09 -> subsequent month is 2026-10
    # Day 15 of 2026-10: 2026-10-15 is Thursday (business day)
    due_dctf = calculate_tax_due_date("2026-09", "DCTFWEB")
    assert due_dctf == date(2026, 10, 15)

    # Day 20 of 2026-10: 2026-10-20 is Tuesday (business day)
    due_das = calculate_tax_due_date("2026-09", "DAS")
    assert due_das == date(2026, 10, 20)

    # For competence 2026-10 -> subsequent month is 2026-11
    # Day 15 of 2026-11: 2026-11-15 is Sunday (holiday Proclamação da República)
    # Friday 2026-11-13 is business day
    due_reinf = calculate_tax_due_date("2026-10", "REINF")
    assert due_reinf == date(2026, 11, 13) # Anticipated to Friday!


def test_mandatory_receipt_requirement_blocks_completion(db_session):
    """DoD: The system must not allow completing a task requiring a receipt without an attached file."""
    task = Task(
        id="task-receipt-01",
        company_id="comp-01",
        competence="2026-09",
        title="Transmitir DCTFWeb",
        statutory_due_date=date(2026, 10, 15),
        internal_deadline=date(2026, 10, 13),
        status="in_progress",
        has_receipt_required=True,
        receipt_file_id=None
    )
    db_session.add(task)
    db_session.commit()

    # Attempting to complete must raise HTTP 400
    with pytest.raises(HTTPException) as exc:
        update_task_status(db_session, "task-receipt-01", TaskStatusUpdate(new_status="completed"))
    assert exc.value.status_code == 400
    assert "recibo" in exc.value.detail.lower()

    # Attach receipt
    attach_task_receipt(db_session, "task-receipt-01", "file-receipt-123", "hashsha256abc123")

    # Now it must succeed
    res = update_task_status(db_session, "task-receipt-01", TaskStatusUpdate(new_status="completed"))
    assert res.status == "completed"
    assert res.receipt_file_id == "file-receipt-123"


def test_task_dependency_dag_blocks_completion(db_session):
    """DoD: Dependent task cannot be completed while prerequisite task is not completed."""
    t_esocial = Task(
        id="task-esocial", company_id="comp-01", competence="2026-09",
        title="Fechar Folha eSocial (S-1299)", statutory_due_date=date(2026, 10, 15),
        internal_deadline=date(2026, 10, 13), status="in_progress", has_receipt_required=False
    )
    t_dctf = Task(
        id="task-dctf", company_id="comp-01", competence="2026-09",
        title="Transmitir DCTFWeb", statutory_due_date=date(2026, 10, 15),
        internal_deadline=date(2026, 10, 13), status="todo", has_receipt_required=False
    )
    db_session.add_all([t_esocial, t_dctf])
    db_session.commit()

    dep = TaskDependency(blocked_task_id="task-dctf", prerequisite_task_id="task-esocial")
    db_session.add(dep)
    db_session.commit()

    # Trying to complete DCTFWeb must fail because eSocial is in_progress
    with pytest.raises(HTTPException) as exc:
        update_task_status(db_session, "task-dctf", TaskStatusUpdate(new_status="completed"))
    assert exc.value.status_code == 400
    assert "bloqueada" in exc.value.detail.lower()

    # Complete eSocial first
    update_task_status(db_session, "task-esocial", TaskStatusUpdate(new_status="completed"))

    # Now DCTFWeb can complete!
    res = update_task_status(db_session, "task-dctf", TaskStatusUpdate(new_status="completed"))
    assert res.status == "completed"


def test_batch_competence_generation(db_session):
    """Validates batch instantiation of recurring tasks for companies."""
    res = generate_tasks_for_competence(
        db_session,
        CompetenceBatchGenerateInput(competence="2026-09"),
        {"comp-01": "simples_nacional", "comp-02": "lucro_presumido"}
    )
    assert res.companies_processed == 2
    assert res.tasks_generated >= 5
    assert len(res.errors) == 0


def test_task_sla_risk_calculation():
    """Validates SLA risk categories: green, yellow, red, overdue."""
    today = date.today()
    assert calculate_task_risk(today, "todo")[0] == "red_critical"
    assert calculate_task_risk(today - date.resolution, "todo")[0] == "overdue"
    assert calculate_task_risk(today + date.resolution * 2, "todo")[0] == "yellow_alert"
    assert calculate_task_risk(today + date.resolution * 10, "todo")[0] == "green"
