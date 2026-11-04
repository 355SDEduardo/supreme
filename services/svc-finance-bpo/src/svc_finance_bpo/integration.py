from datetime import date
from decimal import Decimal
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Text
from sqlalchemy.orm import Session
from supreme_common.auth_context import context, require_role
from supreme_common.events import publish
from .database import Base, get_db
from .models import PayableReceivableBill
from .schemas import BillCreate, BillResponse

class Settlement(Base):
    __tablename__ = 'settlements'
    id = Column(String(100), primary_key=True)
    payload_hash = Column(String(64), nullable=False)
    result = Column(Text, nullable=False)

class SettlementInput(BaseModel):
    transaction_id: str
    bill_ids: list[str] = Field(min_length=1, max_length=100)
    amount: Decimal
    payment_date: date

integration_router = APIRouter()

@integration_router.post('/bills/receivable',response_model=BillResponse)
def receivable(payload: BillCreate, db: Session = Depends(get_db)):
    from .service import create_bill
    payload.type='receivable'
    return create_bill(db,payload,created_by_user_id=context()['sub'])

@integration_router.post('/bills/{bill_id}/dispatch-reminder')
def reminder(bill_id: str, db: Session = Depends(get_db)):
    if not db.query(PayableReceivableBill).filter(PayableReceivableBill.id==bill_id).first():
        raise HTTPException(404,'Título não encontrado.')
    raise HTTPException(501,'Configure o conector de mensagens antes de disparar lembretes.')

def serialize(bill):
    return {column.name: getattr(bill, column.name) for column in bill.__table__.columns}

@integration_router.get('/internal/bills/open')
@integration_router.get('/bills/open')
def open_bills(db: Session = Depends(get_db)):
    return [serialize(b) for b in db.query(PayableReceivableBill).filter(
        PayableReceivableBill.status.in_(['approved','scheduled','pending_approval'])).all()]

@integration_router.get('/bills')
def list_bills(db: Session = Depends(get_db)):
    return [serialize(b) for b in db.query(PayableReceivableBill).all()]

@integration_router.post('/internal/bills/settle')
def settle(payload: SettlementInput, db: Session = Depends(get_db)):
    require_role('service', 'super_admin', 'supervisor', 'bpo_operator')
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    existing = db.query(Settlement).filter(Settlement.id == payload.transaction_id).first()
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, 'Transação já utilizada com outros títulos ou valores.')
        return json.loads(existing.result)
    if len(set(payload.bill_ids)) != len(payload.bill_ids):
        raise HTTPException(422, 'Títulos duplicados na solicitação.')
    bills = db.query(PayableReceivableBill).filter(PayableReceivableBill.id.in_(payload.bill_ids)).with_for_update().all()
    if len(bills) != len(payload.bill_ids):
        raise HTTPException(404, 'Título não encontrado neste contexto.')
    expected_type = 'payable' if payload.amount < 0 else 'receivable'
    if any(b.status not in {'approved','scheduled'} or b.type != expected_type for b in bills):
        raise HTTPException(409, 'Aprovação e direção dos títulos devem corresponder ao movimento bancário.')
    if sum((b.final_amount for b in bills), Decimal('0')) != abs(payload.amount):
        raise HTTPException(409, 'A soma dos títulos não corresponde ao valor da transação.')
    from sqlalchemy import update
    table=PayableReceivableBill.__table__
    changed=db.connection().execute(update(table).where(table.c.id.in_(payload.bill_ids),
        table.c.organization_id==context()['organization_id'],table.c.company_id==context()['company_id'],
        table.c.status.in_(['approved','scheduled'])).values(status='paid',payment_date=payload.payment_date))
    if changed.rowcount!=len(bills):
        db.rollback()
        raise HTTPException(409,'Um dos títulos já foi liquidado por outra operação.')
    for bill in bills:
        bill.status, bill.payment_date = 'paid', payload.payment_date
    result = {'status': 'settled', 'bill_ids': payload.bill_ids, 'transaction_id': payload.transaction_id}
    db.add(Settlement(id=payload.transaction_id, payload_hash=digest, result=json.dumps(result)))
    db.commit()
    for bill in bills:
        publish('BillSettled', {'bill': serialize(bill)}, event_id='bill-settled-' + payload.transaction_id + '-' + bill.id)
    return result
