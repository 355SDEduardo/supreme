"""Pydantic schemas for Feature 03: Conciliação Bancária Automática."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BankAccountResponse(BaseModel):
    id: str
    company_id: str
    bank_code: str
    bank_name: str
    agency_number: str
    account_number: str
    current_balance: float
    is_active: bool


class StatementImportResponse(BaseModel):
    statement_id: str
    total_transactions_parsed: int
    imported_count: int
    duplicates_skipped_count: int
    period_start: date
    period_end: date
    opening_balance: float
    closing_balance: float


class BankTransactionResponse(BaseModel):
    id: str
    bank_account_id: str
    fitid: str
    transaction_date: date
    amount: float
    memo: str
    document_number: Optional[str]
    status: str


class SuggestionItem(BaseModel):
    transaction_id: str
    fitid: str
    amount: float
    transaction_date: str
    memo: str
    best_match_bill_id: Optional[str]
    bill_title: Optional[str]
    confidence_score: int
    match_category: str


class ConfirmReconciliationInput(BaseModel):
    company_id: str
    bank_account_id: str
    transaction_id: str
    bill_ids: List[str]
    match_type: str = "exact_1_1"  # exact_1_1, grouped_1_n, grouped_n_1


class ConfirmReconciliationResponse(BaseModel):
    reconciliation_id: str
    status: str
    difference_amount: float
    message: str


class QuickExpenseInput(BaseModel):
    company_id: str
    bank_account_id: str
    transaction_id: str
    category_name: str = "Tarifas Bancárias"
    notes: Optional[str] = None


class BalanceCheckResponse(BaseModel):
    bank_account_id: str
    opening_balance: float
    total_inflows: float
    total_outflows: float
    calculated_balance: float
    statement_closing_balance: float
    difference: float
    can_lock_period: bool
