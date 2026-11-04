"""FastAPI Router for Feature 03: Conciliação Bancária Automática."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from portalcontabilidades.core.database import get_db

from .schemas import (
    BankAccountResponse, StatementImportResponse, BankTransactionResponse,
    SuggestionItem, ConfirmReconciliationInput, ConfirmReconciliationResponse,
    QuickExpenseInput, BalanceCheckResponse
)
from .models import BankAccount, BankTransaction
from .service import (
    import_ofx_statement, confirm_reconciliation, quick_reconcile_expense,
    check_account_balance
)
from .matching_engine import find_matching_candidates

router = APIRouter(tags=["Feature 03: Conciliação Bancária Automática"])


@router.post("/bank-accounts/{account_id}/statements/import-ofx", response_model=StatementImportResponse)
async def import_ofx(
    account_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import and process OFX banking statements with FITID deduplication."""
    content_bytes = await file.read()
    content_str = content_bytes.decode("utf-8", errors="ignore")
    return import_ofx_statement(db=db, bank_account_id=account_id, ofx_content_str=content_str)


@router.get("/bank-accounts/{account_id}/transactions/unmatched", response_model=List[BankTransactionResponse])
def get_unmatched_transactions(
    account_id: str,
    db: Session = Depends(get_db)
):
    """List pending transactions requiring reconciliation."""
    trxs = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == account_id,
        BankTransaction.status == "pending"
    ).order_by(BankTransaction.transaction_date.desc()).all()
    return trxs


@router.post("/reconciliations/suggest", response_model=List[SuggestionItem])
def get_matching_suggestions(
    account_id: str,
    db: Session = Depends(get_db)
):
    """Runs matching engine across unmatched transactions with confidence scores."""
    unmatched = db.query(BankTransaction).filter(
        BankTransaction.bank_account_id == account_id,
        BankTransaction.status == "pending"
    ).all()

    trx_dicts = [
        {
            "id": t.id,
            "fitid": t.fitid,
            "amount": t.amount,
            "transaction_date": t.transaction_date,
            "memo": t.memo
        }
        for t in unmatched
    ]

    # In a full deployment, open bills are fetched from Feature 04
    open_bills = []
    suggestions = find_matching_candidates(trx_dicts, open_bills)
    return suggestions


@router.post("/reconciliations/confirm", response_model=ConfirmReconciliationResponse)
def reconcile_transaction(
    payload: ConfirmReconciliationInput,
    db: Session = Depends(get_db)
):
    """Confirm matching between transaction and bills."""
    return confirm_reconciliation(db=db, input_data=payload)


@router.post("/reconciliations/quick-expense", response_model=ConfirmReconciliationResponse)
def reconcile_quick_expense(
    payload: QuickExpenseInput,
    db: Session = Depends(get_db)
):
    """Instant 1-click reconciliation for bank tariffs and yields."""
    return quick_reconcile_expense(db=db, input_data=payload)


@router.get("/bank-accounts/{account_id}/balance-check", response_model=BalanceCheckResponse)
def get_balance_check(
    account_id: str,
    db: Session = Depends(get_db)
):
    """Mathematical verification: Opening + In - Out == Closing Balance."""
    return check_account_balance(db=db, bank_account_id=account_id)
