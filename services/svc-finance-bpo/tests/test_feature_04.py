"""Unit and Integration Tests for Feature 04: Contas a Pagar e Receber."""


import pytest
from datetime import date
from decimal import Decimal
from fastapi import HTTPException

from svc_finance_bpo.models import PayableReceivableBill, BillApproval
from svc_finance_bpo.barcode_validator import validate_linha_digitavel, calculate_mod10
from svc_finance_bpo.pix_validator import validate_pix_key, validate_pix_emv_payload
from svc_finance_bpo.approval_engine import can_user_approve_bill, determine_required_approvals
from svc_finance_bpo.aging_calculator import calculate_late_penalties, calculate_aging_list
from svc_finance_bpo.service import (
    create_bill, approve_bill, reject_bill, get_aging_list_data
)
from svc_finance_bpo.schemas import (
    BillCreate, BillApprovalInput, BillRejectInput
)


def test_febraban_linha_digitavel_validation():
    """Validates 47-digit bank collection line and check digit verification."""
    # Valid linha digitavel: 34191.09008 00000.276402 00416.710002 1 98450000015000
    # Field 1 DV: 8, Field 2 DV: 2, Field 3 DV: 2
    linha_valida = "34191.09008 00000.276402 00416.710002 1 98450000015000"
    is_valid, msg, details = validate_linha_digitavel(linha_valida)
    assert is_valid is True
    assert details["amount"] == Decimal("150.00")
    assert details["type"] == "boleto_bancario"

    # Corrupt check digit in field 1 (replace '8' with '9')
    linha_invalida = "34191.09009 00000.276402 00416.710002 1 98450000015000"
    is_valid_bad, msg_bad, _ = validate_linha_digitavel(linha_invalida)
    assert is_valid_bad is False
    assert "1º campo" in msg_bad


def test_pix_key_validation():
    """Validates PIX key types: CPF, CNPJ, email, phone E.164, and UUID EVP."""
    # CPF (valid checksum)
    assert validate_pix_key("529.982.247-25")[0] is True
    assert validate_pix_key("000.000.000-00")[0] is False
    # CNPJ
    assert validate_pix_key("11.222.333/0001-81")[0] is True
    # Email
    assert validate_pix_key("financeiro@empresa.com.br")[0] is True
    assert validate_pix_key("invalid-email-sem-arroba")[0] is False
    # Phone (must have international +)
    assert validate_pix_key("+5511999998888")[0] is True
    assert validate_pix_key("11999998888")[0] is False  # Missing international +55
    # Random key (UUID)
    assert validate_pix_key("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")[0] is True


def test_duplicate_bill_blocking(db_session):
    """DoD: System must block registration of duplicate titles (same counterparty, doc number, and amount)."""
    bill_data = BillCreate(
        company_id="comp-dup-01",
        counterparty_name="Distribuidora Delta",
        document_number="NF-9988",
        original_amount=1250.00,
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 9, 20)
    )
    b1 = create_bill(db_session, bill_data)
    assert b1.id is not None

    # Attempt duplicate
    with pytest.raises(HTTPException) as exc:
        create_bill(db_session, bill_data)
    assert exc.value.status_code == 400
    assert "duplicidade" in exc.value.detail.lower()


def test_segregation_of_duties_and_tiered_approvals(db_session):
    """DoD: BPO operator cannot self-approve; titles > R$ 2,000 require 2 approval levels."""
    high_value_bill_data = BillCreate(
        company_id="comp-appr-01",
        counterparty_name="Locadora de Máquinas",
        document_number="DOC-123",
        original_amount=5000.00, # Requires 2 approval levels (> 2000.00)
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 9, 25)
    )
    bill = create_bill(db_session, high_value_bill_data, created_by_user_id="bpo-operator-01")
    assert bill.status == "pending_approval"
    assert bill.required_approvals == 2

    # 1. BPO Preparer attempts self-approval -> Must be blocked (403)
    with pytest.raises(HTTPException) as exc:
        approve_bill(
            db_session,
            bill.id,
            BillApprovalInput(user_id="bpo-operator-01", user_role="bpo_operator")
        )
    assert exc.value.status_code == 403
    assert "segregação" in exc.value.detail.lower()

    # 2. First approval by client manager -> status remains pending_approval (level 1 of 2)
    b_step1 = approve_bill(
        db_session,
        bill.id,
        BillApprovalInput(user_id="client-manager-01", user_role="client_admin")
    )
    assert b_step1.current_approvals == 1
    assert b_step1.status == "pending_approval"

    # 3. Second approval by director -> reaches threshold, status transitions to approved
    b_step2 = approve_bill(
        db_session,
        bill.id,
        BillApprovalInput(user_id="client-director-02", user_role="client_admin")
    )
    assert b_step2.current_approvals == 2
    assert b_step2.status == "approved"


def test_bill_rejection_with_mandatory_reason(db_session):
    """Validates bill rejection flow."""
    bill = create_bill(
        db_session,
        BillCreate(
            company_id="comp-01",
            counterparty_name="Serviços Gerais",
            original_amount=800.00,
            issue_date=date(2026, 9, 1),
            due_date=date(2026, 9, 10)
        )
    )
    rejected = reject_bill(
        db_session,
        bill.id,
        BillRejectInput(user_id="manager-01", reason="Serviço não homologado pela diretoria")
    )
    assert rejected.status == "rejected"
    assert "homologado" in rejected.rejection_reason


def test_late_penalties_and_aging_calculation():
    """Validates pro-rata interest and Aging List brackets."""
    due = date(2026, 9, 1)
    calc_date = date(2026, 9, 31) if False else date(2026, 10, 1) # 30 days overdue
    penalty, interest, total = calculate_late_penalties(Decimal("1000.00"), due, calc_date)

    # 2% fixed fine on 1000 = 20.00
    assert penalty == Decimal("20.00")
    # 1% monthly interest on 1000 for 30 days = 10.00
    assert interest == Decimal("10.00")
    assert total == Decimal("1030.00")

    # Aging List aggregation
    bills = [
        {"id": "b1", "final_amount": 1000.0, "due_date": date(2026, 10, 15)}, # A vencer (<30d)
        {"id": "b2", "final_amount": 500.0, "due_date": date(2026, 9, 15)},  # Vencido (<30d)
    ]
    aging = calculate_aging_list(bills, date(2026, 10, 1))
    assert aging["total_receivables"] == 1500.0
    assert aging["total_overdue"] == 500.0
    assert aging["default_rate_pct"] > 0
