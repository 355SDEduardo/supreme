from datetime import date
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from supreme_common.auth_context import context
from supreme_common.events import publish
from supreme_common.http_client import service_request
from .database import get_db
from .models import BankAccount, BankTransaction
from .schemas import ConfirmReconciliationInput, ConfirmReconciliationResponse
from .service import confirm_reconciliation
from .matching_engine import find_matching_candidates

integration_router = APIRouter()

class AccountInput(BaseModel):
    bank_code: str
    bank_name: str = ''
    agency_number: str
    account_number: str

@integration_router.post('/bank-accounts', status_code=201)
def create_account(payload: AccountInput, db: Session = Depends(get_db)):
    fields = payload.model_dump()
    # Map to the existing model without accepting tenant identifiers from clients.
    account = BankAccount(company_id=context()['company_id'], **fields)
    db.add(account)
    db.commit()
    return {'id': account.id}

@integration_router.get('/bank-accounts')
def accounts(db: Session = Depends(get_db)):
    return [{column.name: getattr(a, column.name) for column in a.__table__.columns} for a in db.query(BankAccount).all()]

@integration_router.post('/reconciliations/suggest')
async def suggest(account_id: str, db: Session = Depends(get_db)):
    if not db.query(BankAccount).filter(BankAccount.id == account_id).first():
        raise HTTPException(404, 'Conta não encontrada.')
    response = await service_request('finance-bpo', 'GET', '/internal/bills/open')
    bills = response.json()
    for bill in bills:
        bill['final_amount'] = Decimal(str(bill['final_amount']))
        bill['due_date'] = date.fromisoformat(bill['due_date'])
    transactions = db.query(BankTransaction).filter(BankTransaction.bank_account_id == account_id, BankTransaction.status == 'pending').all()
    return find_matching_candidates([{'id': t.id, 'fitid': t.fitid, 'amount': t.amount,
        'transaction_date': t.transaction_date, 'memo': t.memo or ''} for t in transactions], bills)

@integration_router.post('/reconciliations/confirm', response_model=ConfirmReconciliationResponse)
async def confirm(payload: ConfirmReconciliationInput, db: Session = Depends(get_db)):
    transaction = db.query(BankTransaction).filter(BankTransaction.id == payload.transaction_id).first()
    if not transaction or transaction.bank_account_id != payload.bank_account_id:
        raise HTTPException(404, 'Transação/conta não encontrada.')
    if transaction.status == 'matched':
        return ConfirmReconciliationResponse(reconciliation_id=transaction.reconciliation_id,
            status='confirmed', difference_amount=0, message='Conciliação já efetivada.')
    operation = str(uuid.uuid5(uuid.NAMESPACE_URL, context()['organization_id'] + ':' + payload.company_id + ':' + transaction.id))
    await service_request('finance-bpo', 'POST', '/internal/bills/settle', json={
        'transaction_id': operation, 'bill_ids': payload.bill_ids, 'amount': str(transaction.amount),
        'payment_date': transaction.transaction_date.isoformat()})
    result = confirm_reconciliation(db, payload, user_id=context()['sub'])
    publish('TransactionReconciled', {'transaction_id': transaction.id, 'reconciliation_id': result.reconciliation_id,
        'amount': str(transaction.amount), 'transaction_date': transaction.transaction_date.isoformat(),
        'bill_ids': payload.bill_ids, 'memo': transaction.memo}, event_id=operation)
    return result
