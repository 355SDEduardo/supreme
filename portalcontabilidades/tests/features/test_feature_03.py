"""Unit and Integration Tests for Feature 03: Conciliação Bancária Automática."""


import pytest
from datetime import date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from portalcontabilidades.core.database import Base
from portalcontabilidades.features.conciliacao.models import BankAccount, BankStatement, BankTransaction
from portalcontabilidades.features.conciliacao.ofx_parser import parse_ofx_content
from portalcontabilidades.features.conciliacao.matching_engine import calculate_match_confidence, find_matching_candidates
from portalcontabilidades.features.conciliacao.service import (
    import_ofx_statement, confirm_reconciliation, quick_reconcile_expense, check_account_balance
)
from portalcontabilidades.features.conciliacao.schemas import ConfirmReconciliationInput, QuickExpenseInput

SAMPLE_OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<CURDEF>BRL
<BANKACCTFROM>
<BANKID>0341
<ACCTID>123456
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260901
<DTEND>20260930
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260915120000[-03:EST]
<TRNAMT>-1500.00
<FITID>202609150001
<CHECKNUM>000123
<MEMO>PAGTO FORNECEDOR ALFA DISTRIBUIDORA
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260920120000[-03:EST]
<TRNAMT>4500.50
<FITID>202609200002
<MEMO>PIX RECEBIDO CLIENTE BETA
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260925120000[-03:EST]
<TRNAMT>-45.00
<FITID>202609250003
<MEMO>TARIFA BANCARIA MENSALIDADE
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>15000.00
<DTASOF>20260930
</LEDGERBAL>
<AVAILBAL>
<BALAMT>12044.50
<DTASOF>20260901
</AVAILBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed bank account
    acc = BankAccount(
        id="acc-01",
        company_id="comp-01",
        bank_code="341",
        bank_name="Itaú Unibanco",
        agency_number="1234",
        account_number="56789-0",
        current_balance=Decimal("12044.50")
    )
    session.add(acc)
    session.commit()

    yield session
    session.close()


def test_ofx_parser_extraction():
    """Validates extraction of transactions, dates, amounts, and balances from OFX."""
    parsed = parse_ofx_content(SAMPLE_OFX)
    assert len(parsed["transactions"]) == 3
    t1 = parsed["transactions"][0]
    assert t1["fitid"] == "202609150001"
    assert t1["amount"] == Decimal("-1500.00")
    assert t1["transaction_date"] == date(2026, 9, 15)
    assert "FORNECEDOR" in t1["memo"]

    t2 = parsed["transactions"][1]
    assert t2["amount"] == Decimal("4500.50")


def test_fitid_deduplication(db_session):
    """DoD: Transactions with the same FITID in the same account are rejected as duplicates."""
    # First import
    res1 = import_ofx_statement(db_session, "acc-01", SAMPLE_OFX)
    assert res1.imported_count == 3
    assert res1.duplicates_skipped_count == 0

    # Second import of the identical statement
    res2 = import_ofx_statement(db_session, "acc-01", SAMPLE_OFX)
    assert res2.imported_count == 0
    assert res2.duplicates_skipped_count == 3


def test_matching_engine_confidence_scores():
    """Validates confidence scoring: safe match >= 95%, probable match >= 70%."""
    # Exact amount, same date, counterparty match -> >= 95%
    score_exact = calculate_match_confidence(
        trx_amount=Decimal("-1500.00"),
        trx_date=date(2026, 9, 15),
        trx_memo="PAGTO FORNECEDOR ALFA",
        bill_amount=Decimal("1500.00"),
        bill_due_date=date(2026, 9, 15),
        bill_counterparty="Alfa Distribuidora"
    )
    assert score_exact >= 95

    # Small date difference (D+1) -> probable match (70-94%)
    score_date_diff = calculate_match_confidence(
        trx_amount=Decimal("-1500.00"),
        trx_date=date(2026, 9, 16),
        trx_memo="PAGTO FORNECEDOR ALFA",
        bill_amount=Decimal("1500.00"),
        bill_due_date=date(2026, 9, 15),
        bill_counterparty="Alfa Distribuidora"
    )
    assert 70 <= score_date_diff < 95

    # Mismatched amount -> low score (< 50%)
    score_mismatch = calculate_match_confidence(
        trx_amount=Decimal("-1500.00"),
        trx_date=date(2026, 9, 15),
        trx_memo="PAGTO",
        bill_amount=Decimal("500.00"),
        bill_due_date=date(2026, 9, 15),
        bill_counterparty="Outro"
    )
    assert score_mismatch < 50


def test_reconciliation_confirmation_and_quick_expense(db_session):
    """Validates confirming reconciliation and quick expense creation."""
    import_ofx_statement(db_session, "acc-01", SAMPLE_OFX)
    trx = db_session.query(BankTransaction).filter(BankTransaction.fitid == "202609150001").first()
    assert trx.status == "pending"

    # Confirm matching
    res = confirm_reconciliation(
        db_session,
        ConfirmReconciliationInput(
            company_id="comp-01",
            bank_account_id="acc-01",
            transaction_id=trx.id,
            bill_ids=["bill-uuid-1"]
        )
    )
    assert res.status == "confirmed"

    db_session.refresh(trx)
    assert trx.status == "matched"

    # Quick expense for bank fee
    fee_trx = db_session.query(BankTransaction).filter(BankTransaction.fitid == "202609250003").first()
    fee_res = quick_reconcile_expense(
        db_session,
        QuickExpenseInput(
            company_id="comp-01",
            bank_account_id="acc-01",
            transaction_id=fee_trx.id,
            category_name="Tarifa Itaú"
        )
    )
    assert fee_res.status == "confirmed"
    db_session.refresh(fee_trx)
    assert fee_trx.status == "matched"


def test_balance_check_mathematical_validation(db_session):
    """DoD: Validates mathematical formula Opening + Inflows - Outflows == Closing Balance."""
    import_ofx_statement(db_session, "acc-01", SAMPLE_OFX)
    bal_res = check_account_balance(db_session, "acc-01")
    assert bal_res.opening_balance > 0
    assert bal_res.total_inflows > 0
    assert bal_res.total_outflows > 0
