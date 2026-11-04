"""Service logic for Feature 03: Conciliação Bancária Automática."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException

from .models import BankAccount, BankStatement, BankTransaction, Reconciliation, ReconciliationItem
from .schemas import (
    StatementImportResponse, ConfirmReconciliationInput,
    ConfirmReconciliationResponse, QuickExpenseInput, BalanceCheckResponse
)
from .ofx_parser import parse_ofx_content
from .matching_engine import find_matching_candidates


def import_ofx_statement(
    db: Session,
    bank_account_id: str,
    ofx_content_str: str
) -> StatementImportResponse:
    """Parses OFX content, enforces FITID deduplication, and records transactions."""
    account = db.query(BankAccount).filter(BankAccount.id == bank_account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada.")

    parsed = parse_ofx_content(ofx_content_str)
    raw_trxs = parsed["transactions"]
    if not raw_trxs:
        raise HTTPException(status_code=400, detail="Nenhuma transação bancária encontrada no arquivo OFX.")

    period_start = min(t["transaction_date"] for t in raw_trxs)
    period_end = max(t["transaction_date"] for t in raw_trxs)

    statement = BankStatement(
        bank_account_id=bank_account_id,
        period_start=period_start,
        period_end=period_end,
        opening_balance=parsed["opening_balance"],
        closing_balance=parsed["closing_balance"],
        status="imported",
        import_date=datetime.now(timezone.utc)
    )
    db.add(statement)
    db.flush()

    imported = 0
    duplicates = 0
    total_credits = Decimal("0.00")
    total_debits = Decimal("0.00")

    for t in raw_trxs:
        # Strict FITID deduplication check
        existing = db.query(BankTransaction).filter(
            BankTransaction.bank_account_id == bank_account_id,
            BankTransaction.fitid == t["fitid"]
        ).first()

        if existing:
            duplicates += 1
            continue

        trx = BankTransaction(
            bank_account_id=bank_account_id,
            statement_id=statement.id,
            fitid=t["fitid"],
            transaction_date=t["transaction_date"],
            amount=t["amount"],
            memo=t["memo"],
            document_number=t.get("document_number"),
            status="pending"
        )
        db.add(trx)
        imported += 1

        if t["amount"] > 0:
            total_credits += t["amount"]
        else:
            total_debits += abs(t["amount"])

    statement.total_credits = total_credits
    statement.total_debits = total_debits
    account.current_balance = parsed["closing_balance"]

    db.commit()
    db.refresh(statement)

    return StatementImportResponse(
        statement_id=statement.id,
        total_transactions_parsed=len(raw_trxs),
        imported_count=imported,
        duplicates_skipped_count=duplicates,
        period_start=period_start,
        period_end=period_end,
        opening_balance=float(parsed["opening_balance"]),
        closing_balance=float(parsed["closing_balance"])
    )


def confirm_reconciliation(
    db: Session,
    input_data: ConfirmReconciliationInput,
    user_id: Optional[str] = None
) -> ConfirmReconciliationResponse:
    """Confirms matching, registers reconciliation, and sets transaction status to 'matched'."""
    trx = db.query(BankTransaction).filter(BankTransaction.id == input_data.transaction_id).first()
    if not trx:
        raise HTTPException(status_code=404, detail="Transação bancária não encontrada.")
    if trx.status == "matched":
        raise HTTPException(status_code=400, detail="Esta transação bancária já foi previamente conciliada.")

    reconciliation = Reconciliation(
        company_id=input_data.company_id,
        bank_account_id=input_data.bank_account_id,
        match_type=input_data.match_type,
        difference_amount=Decimal("0.00"),
        reconciled_by=user_id,
        reconciled_at=datetime.now(timezone.utc)
    )
    db.add(reconciliation)
    db.flush()

    for bill_id in input_data.bill_ids:
        item = ReconciliationItem(
            reconciliation_id=reconciliation.id,
            bank_transaction_id=trx.id,
            bill_id=bill_id,
            allocated_amount=abs(trx.amount) / len(input_data.bill_ids)
        )
        db.add(item)

    trx.status = "matched"
    trx.reconciliation_id = reconciliation.id

    db.commit()
    return ConfirmReconciliationResponse(
        reconciliation_id=reconciliation.id,
        status="confirmed",
        difference_amount=0.00,
        message="Conciliação bancária efetivada com sucesso."
    )


def quick_reconcile_expense(
    db: Session,
    input_data: QuickExpenseInput,
    user_id: Optional[str] = None
) -> ConfirmReconciliationResponse:
    """Instantly reconciles bank fees or yield without requiring prior bill registration."""
    trx = db.query(BankTransaction).filter(BankTransaction.id == input_data.transaction_id).first()
    if not trx:
        raise HTTPException(status_code=404, detail="Transação não encontrada.")

    reconciliation = Reconciliation(
        company_id=input_data.company_id,
        bank_account_id=input_data.bank_account_id,
        match_type="manual_adjustment",
        difference_amount=Decimal("0.00"),
        reconciled_by=user_id,
        reconciled_at=datetime.now(timezone.utc)
    )
    db.add(reconciliation)
    db.flush()

    db.add(ReconciliationItem(
        reconciliation_id=reconciliation.id,
        bank_transaction_id=trx.id,
        bill_id=None,
        allocated_amount=abs(trx.amount)
    ))

    trx.status = "matched"
    trx.reconciliation_id = reconciliation.id

    db.commit()
    return ConfirmReconciliationResponse(
        reconciliation_id=reconciliation.id,
        status="confirmed",
        difference_amount=0.00,
        message=f"Lançamento avulso '{input_data.category_name}' conciliado com sucesso."
    )


def check_account_balance(db: Session, bank_account_id: str) -> BalanceCheckResponse:
    """Verifies: Opening Balance + Inflows - Outflows == Statement Closing Balance."""
    statement = db.query(BankStatement).filter(
        BankStatement.bank_account_id == bank_account_id
    ).order_by(BankStatement.import_date.desc()).first()

    if not statement:
        return BalanceCheckResponse(
            bank_account_id=bank_account_id,
            opening_balance=0.0,
            total_inflows=0.0,
            total_outflows=0.0,
            calculated_balance=0.0,
            statement_closing_balance=0.0,
            difference=0.0,
            can_lock_period=False
        )

    opening = statement.opening_balance
    inflows = statement.total_credits
    outflows = statement.total_debits
    calculated = opening + inflows - outflows
    stmt_closing = statement.closing_balance

    diff = abs(calculated - stmt_closing)
    can_lock = (diff == Decimal("0.00"))

    return BalanceCheckResponse(
        bank_account_id=bank_account_id,
        opening_balance=float(opening),
        total_inflows=float(inflows),
        total_outflows=float(outflows),
        calculated_balance=float(calculated),
        statement_closing_balance=float(stmt_closing),
        difference=float(diff),
        can_lock_period=can_lock
    )
