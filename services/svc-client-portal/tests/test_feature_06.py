"""Unit and Integration Tests for Feature 06: Portal do Cliente e Comunicação."""


import pytest
from datetime import datetime, timezone
from fastapi import HTTPException

from svc_client_portal.models import ClientTicket, TicketMessage, DocumentDownloadReceipt
from svc_client_portal.ticket_validator import validate_structured_ticket_data, calculate_ticket_sla
from svc_client_portal.service import (
    create_client_ticket, add_ticket_message, record_guide_receipt_confirmation
)
from svc_client_portal.schemas import (
    TicketCreate, TicketMessageCreate, GuideReceiptConfirmInput
)


def test_structured_form_validation():
    """DoD: Every client request via structured form must validate mandatory category fields."""
    # 1. Valid admission
    valid_admission = {
        "employee_name": "Carlos Silva",
        "cpf": "529.982.247-25", # Valid CPF checksum
        "position": "Analista Financeiro",
        "salary": 4500.00,
        "start_date": "2026-11-01"
    }
    is_valid, err = validate_structured_ticket_data("admission", valid_admission)
    assert is_valid is True
    assert err is None

    # 2. Incomplete admission (missing salary)
    incomplete_admission = {
        "employee_name": "Carlos Silva",
        "cpf": "529.982.247-25",
        "position": "Analista"
    }
    is_valid, err = validate_structured_ticket_data("admission", incomplete_admission)
    assert is_valid is False
    assert "salary" in err.lower()

    # 3. Invalid CPF in admission
    bad_cpf_admission = {
        "employee_name": "Carlos Silva",
        "cpf": "000.000.000-00",
        "position": "Analista",
        "salary": 3000.00,
        "start_date": "2026-11-01"
    }
    is_valid, err = validate_structured_ticket_data("admission", bad_cpf_admission)
    assert is_valid is False
    assert "cpf" in err.lower()


def test_ticket_creation_and_sla_assignment(db_session):
    """Validates ticket persistence and dynamic SLA calculation."""
    payload = TicketCreate(
        company_id="comp-ticket-01",
        category="admission",
        title="Solicitação de Admissão - Novo Analista",
        priority="urgent", # 4 hours SLA
        user_id="user-client-01",
        structured_data={
            "employee_name": "Mariana Santos",
            "cpf": "52998224725",
            "position": "Desenvolvedora",
            "salary": 8000.00,
            "start_date": "2026-10-15"
        }
    )
    ticket = create_client_ticket(db_session, payload)
    assert ticket.id is not None
    assert ticket.sla_hours == 4
    assert ticket.status == "open"


def test_ticket_messaging_thread(db_session):
    """Validates ticket interaction and message appending."""
    ticket = create_client_ticket(
        db_session,
        TicketCreate(
            company_id="comp-ticket-01",
            category="fiscal",
            title="Dúvida sobre alíquota ISS",
            user_id="user-client-01"
        )
    )
    msg = add_ticket_message(
        db_session,
        ticket.id,
        TicketMessageCreate(
            sender_id="user-client-01",
            sender_type="client_user",
            message_body="Gostaria de confirmar se a alíquota de ISS para serviços de TI é 2% ou 5% no município de São Paulo."
        )
    )
    assert msg.id is not None
    assert msg.ticket_id == ticket.id


def test_guide_receipt_irrefutable_proof(db_session):
    """DoD: The system must irrefutably log when a tax guide or payslip was downloaded/viewed (timestamp + IP + user)."""
    confirm_input = GuideReceiptConfirmInput(
        document_id="doc-guide-das-99",
        company_id="comp-ticket-01",
        user_id="user-client-01",
        action_type="viewed_and_confirmed"
    )
    res = record_guide_receipt_confirmation(
        db=db_session,
        data=confirm_input,
        ip_address="177.135.20.10",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)"
    )
    assert res.receipt_id is not None
    assert res.ip_address == "177.135.20.10"

    # Verify database persistence
    saved = db_session.query(DocumentDownloadReceipt).filter(
        DocumentDownloadReceipt.id == res.receipt_id
    ).first()
    assert saved is not None
    assert saved.document_id == "doc-guide-das-99"
    assert saved.downloaded_at is not None
