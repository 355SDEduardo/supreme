"""Parser for Brazilian Bank Statements in OFX 1.x (SGML) and OFX 2.x (XML) formats."""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional


def parse_ofx_date(date_str: str) -> date:
    """Parses OFX dates like '20260915120000[-03:BRT]' or '20260915'."""
    clean = re.sub(r"\[.*\]", "", date_str.strip())
    raw_digits = clean[:8]
    if len(raw_digits) == 8:
        return datetime.strptime(raw_digits, "%Y%m%d").date()
    return date.today()


def parse_ofx_content(content_str: str) -> Dict[str, Any]:
    """Robust parser for both SGML (OFX 1.x) and XML (OFX 2.x) banking statements.
    Extracts transactions (<STMTTRN>), ledger balances, and bank account metadata.
    """
    # 1. Normalize line breaks
    normalized = content_str.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Extract Opening and Closing balances if present
    opening_bal = Decimal("0.00")
    closing_bal = Decimal("0.00")

    ledger_bal_match = re.search(r"<LEDGERBAL>[\s\S]*?<BALAMT>([\-\d\.,]+)", normalized, re.IGNORECASE)
    if ledger_bal_match:
        closing_bal = Decimal(ledger_bal_match.group(1).replace(",", "."))

    avail_bal_match = re.search(r"<AVAILBAL>[\s\S]*?<BALAMT>([\-\d\.,]+)", normalized, re.IGNORECASE)
    if avail_bal_match:
        opening_bal = Decimal(avail_bal_match.group(1).replace(",", "."))
    else:
        opening_bal = closing_bal

    # 3. Extract Transactions (<STMTTRN> blocks)
    transactions: List[Dict[str, Any]] = []
    # Match everything between <STMTTRN> and </STMTTRN> or next <STMTTRN>
    trn_blocks = re.findall(r"<STMTTRN>([\s\S]*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", normalized, re.IGNORECASE)

    for block in trn_blocks:
        trn_type = re.search(r"<TRNTYPE>([^\s<]+)", block, re.IGNORECASE)
        dt_posted = re.search(r"<DTPOSTED>([^\s<]+)", block, re.IGNORECASE)
        trn_amt = re.search(r"<TRNAMT>([^\s<]+)", block, re.IGNORECASE)
        fitid = re.search(r"<FITID>([^\s<]+)", block, re.IGNORECASE)
        memo = re.search(r"<MEMO>([^\r\n<]+)", block, re.IGNORECASE)
        checknum = re.search(r"<CHECKNUM>([^\s<]+)", block, re.IGNORECASE)

        if trn_amt and fitid and dt_posted:
            amt_str = trn_amt.group(1).replace(",", ".")
            amount_dec = Decimal(amt_str)
            trans_date = parse_ofx_date(dt_posted.group(1))
            memo_text = memo.group(1).strip() if memo else "Transação Bancária"
            fitid_val = fitid.group(1).strip()

            transactions.append({
                "fitid": fitid_val,
                "transaction_date": trans_date,
                "amount": amount_dec,
                "type": trn_type.group(1).upper() if trn_type else ("CREDIT" if amount_dec > 0 else "DEBIT"),
                "memo": memo_text,
                "document_number": checknum.group(1).strip() if checknum else None
            })

    return {
        "opening_balance": opening_bal,
        "closing_balance": closing_bal,
        "transactions": transactions
    }
