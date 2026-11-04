"""Service logic for Feature 04: Contas a Pagar e Receber."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import PayableReceivableBill, BillApproval, BillingLog
from .schemas import (
    BillCreate, BillApprovalInput, BillRejectInput
)
from .barcode_validator import validate_linha_digitavel
from .pix_validator import validate_pix_key, validate_pix_emv_payload
from .approval_engine import determine_required_approvals, can_user_approve_bill
from .aging_calculator import calculate_aging_list, calculate_late_penalties


def create_bill(
    db: Session,
    data: BillCreate,
    created_by_user_id: Optional[str] = None
) -> PayableReceivableBill:
    """Creates a payable or receivable bill with validations and duplicate detection."""
    orig = Decimal(str(data.original_amount))
    disc = Decimal(str(data.discount_amount))
    pen = Decimal(str(data.interest_penalty_amount))
    final = orig - disc + pen

    # 1. Barcode validation if provided
    if data.barcode_line:
        is_valid, msg, _ = validate_linha_digitavel(data.barcode_line)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Código de barras / linha digitável inválido: {msg}")

    # 2. PIX validation if provided
    if data.pix_key:
        is_valid, _, msg = validate_pix_key(data.pix_key)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Chave PIX inválida: {msg}")
    if data.pix_emv_payload:
        is_valid, msg = validate_pix_emv_payload(data.pix_emv_payload)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Payload PIX Copia e Cola inválido: {msg}")

    # 3. Duplicate Bill Detection
    if data.document_number:
        duplicate = db.query(PayableReceivableBill).filter(
            PayableReceivableBill.company_id == data.company_id,
            PayableReceivableBill.counterparty_name == data.counterparty_name,
            PayableReceivableBill.document_number == data.document_number,
            PayableReceivableBill.final_amount == final
        ).first()
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail="Título em duplicidade detectado: mesmo favorecido, mesmo número de documento e mesmo valor."
            )

    required_levels = determine_required_approvals(final) if data.type == "payable" else 0
    initial_status = "pending_approval" if data.type == "payable" else "approved"

    bill = PayableReceivableBill(
        company_id=data.company_id,
        type=data.type,
        counterparty_name=data.counterparty_name,
        counterparty_tax_id=data.counterparty_tax_id,
        document_number=data.document_number,
        original_amount=orig,
        discount_amount=disc,
        interest_penalty_amount=pen,
        final_amount=final,
        issue_date=data.issue_date,
        due_date=data.due_date,
        payment_method=data.payment_method,
        barcode_line=data.barcode_line,
        pix_key=data.pix_key,
        pix_emv_payload=data.pix_emv_payload,
        status=initial_status,
        created_by_user_id=created_by_user_id,
        required_approvals=required_levels,
        current_approvals=0,
        created_at=datetime.now(timezone.utc)
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


def approve_bill(
    db: Session,
    bill_id: str,
    input_data: BillApprovalInput,
    ip_address: str = "127.0.0.1"
) -> PayableReceivableBill:
    """Registers approval, checking duties segregation and approval tiers."""
    bill = db.query(PayableReceivableBill).filter(PayableReceivableBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Título não encontrado.")
    if bill.status in ("approved", "paid", "canceled"):
        raise HTTPException(status_code=400, detail=f"Título não pode ser aprovado no status atual ('{bill.status}').")

    # Segregation of Duties check
    can_appr, reason = can_user_approve_bill(
        user_id=input_data.user_id,
        user_role=input_data.user_role,
        bill_creator_id=bill.created_by_user_id or "",
        current_level=bill.current_approvals + 1
    )
    if not can_appr:
        raise HTTPException(status_code=403, detail=reason)

    bill.current_approvals += 1

    approval = BillApproval(
        bill_id=bill.id,
        approver_user_id=input_data.user_id,
        level=bill.current_approvals,
        status="approved",
        comments=input_data.comments,
        ip_address=ip_address,
        approved_at=datetime.now(timezone.utc)
    )
    db.add(approval)

    # Transition to approved if reached threshold
    if bill.current_approvals >= bill.required_approvals:
        bill.status = "approved"

    db.commit()
    db.refresh(bill)
    return bill


def reject_bill(
    db: Session,
    bill_id: str,
    input_data: BillRejectInput,
    ip_address: str = "127.0.0.1"
) -> PayableReceivableBill:
    """Rejects bill with mandatory justification reason."""
    bill = db.query(PayableReceivableBill).filter(PayableReceivableBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Título não encontrado.")

    bill.status = "rejected"
    bill.rejection_reason = input_data.reason

    db.add(BillApproval(
        bill_id=bill.id,
        approver_user_id=input_data.user_id,
        level=bill.current_approvals + 1,
        status="rejected",
        comments=input_data.reason,
        ip_address=ip_address,
        approved_at=datetime.now(timezone.utc)
    ))

    db.commit()
    db.refresh(bill)
    return bill


def get_aging_list_data(db: Session, company_id: str) -> Dict[str, Any]:
    """Generates aging list metrics for all open receivables of the company."""
    receivables = db.query(PayableReceivableBill).filter(
        PayableReceivableBill.company_id == company_id,
        PayableReceivableBill.type == "receivable",
        PayableReceivableBill.status.in_(["approved", "draft"])
    ).all()

    bill_dicts = [
        {
            "id": r.id,
            "final_amount": r.final_amount,
            "due_date": r.due_date,
            "counterparty_name": r.counterparty_name
        }
        for r in receivables
    ]
    return calculate_aging_list(bill_dicts, date.today())
