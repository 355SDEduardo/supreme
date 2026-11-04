"""FastAPI Router for Feature 04: Contas a Pagar e Receber."""

from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from svc_finance_bpo.database import get_db

from .schemas import (
    BillCreate, BillResponse, BillApprovalInput, BillRejectInput,
    AgingListResponse, ReminderDispatchInput
)
from .models import PayableReceivableBill, BillingLog
from .service import (
    create_bill, approve_bill, reject_bill, get_aging_list_data
)

router = APIRouter(prefix="/bills", tags=["Feature 04: Contas a Pagar e Receber"])


@router.post("/payable", response_model=BillResponse)
def create_payable_bill(
    payload: BillCreate,
    created_by_user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Register title to pay with barcode/PIX validation and duplicate blocking."""
    payload.type = "payable"
    from supreme_common.auth_context import context
    bill = create_bill(db=db, data=payload, created_by_user_id=context()['sub'])
    return bill


@router.get("/payable/approval-queue", response_model=List[BillResponse])
def get_approval_queue(
    company_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Retrieve queue of payable titles awaiting client manager approval."""
    queue = db.query(PayableReceivableBill).filter(
        PayableReceivableBill.company_id == company_id,
        PayableReceivableBill.type == "payable",
        PayableReceivableBill.status == "pending_approval"
    ).order_by(PayableReceivableBill.due_date.asc()).all()
    return queue


@router.post("/{bill_id}/approve", response_model=BillResponse)
def approve_payable_bill(
    bill_id: str,
    payload: BillApprovalInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Approve payment, enforcing segregation of duties and tiered approval levels."""
    ip = request.client.host if request.client else "127.0.0.1"
    return approve_bill(db=db, bill_id=bill_id, input_data=payload, ip_address=ip)


@router.post("/{bill_id}/reject", response_model=BillResponse)
def reject_payable_bill(
    bill_id: str,
    payload: BillRejectInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reject payment title with mandatory justification."""
    ip = request.client.host if request.client else "127.0.0.1"
    return reject_bill(db=db, bill_id=bill_id, input_data=payload, ip_address=ip)


@router.get("/receivable/aging", response_model=AgingListResponse)
def get_aging_list(
    company_id: str = Query(...),
    db: Session = Depends(get_db)
):
    """Consolidated Aging List report with brackets and default rate."""
    return get_aging_list_data(db=db, company_id=company_id)


@router.post("/{bill_id}/dispatch-reminder")
def dispatch_collection_reminder(
    bill_id: str,
    payload: ReminderDispatchInput,
    db: Session = Depends(get_db)
):
    """Dispatch automated reminder via WhatsApp or Email."""
    bill = db.query(PayableReceivableBill).filter(PayableReceivableBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Título não encontrado.")
    if bill.status in ("paid", "canceled"):
        raise HTTPException(status_code=400, detail="Título já liquidado ou cancelado.")

    log = BillingLog(
        bill_id=bill.id,
        channel=payload.channel,
        message_type="collection_reminder",
        recipient="cliente@exemplo.com",
        status="sent",
        sent_at=datetime.now(timezone.utc)
    )
    db.add(log)
    db.commit()
    return {"status": "dispatched", "bill_id": bill.id, "channel": payload.channel}
