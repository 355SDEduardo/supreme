"""Bank reconciliation matching engine with confidence scoring (1:1, 1:N, N:1)."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional


def calculate_match_confidence(
    trx_amount: Decimal,
    trx_date: date,
    trx_memo: str,
    bill_amount: Decimal,
    bill_due_date: date,
    bill_counterparty: str
) -> int:
    """Calculates matching confidence score (0 to 100%).
    Factors: amount matching (exact vs difference), date proximity (D-2 to D+2), memo similarity.
    """
    score = 0
    abs_trx = abs(trx_amount)
    abs_bill = abs(bill_amount)

    # 1. Amount Comparison
    diff_amount = abs(abs_trx - abs_bill)
    if diff_amount == Decimal("0.00"):
        score += 65
    elif diff_amount / max(abs_trx, abs_bill) <= Decimal("0.05"):
        # Small discrepancy (fine/interest or discount)
        score += 45
    else:
        return 20  # Significant amount mismatch

    # 2. Date Proximity
    day_diff = abs((trx_date - bill_due_date).days)
    if day_diff == 0:
        score += 25
    elif day_diff <= 2:
        score += 18
    elif day_diff <= 5:
        score += 10

    # 3. Text/Counterparty overlap
    memo_lower = trx_memo.lower()
    counterparty_words = bill_counterparty.lower().split()
    if any(word in memo_lower for word in counterparty_words if len(word) > 3):
        score += 10

    return min(100, score)


def find_matching_candidates(
    transactions: List[Dict[str, Any]],
    bills: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Analyzes pending transactions against open bills, producing suggestions categorized by confidence score."""
    suggestions: List[Dict[str, Any]] = []

    for trx in transactions:
        best_candidate = None
        best_score = 0

        for b in bills:
            # Check direction: negative trx = payable, positive trx = receivable
            if (trx["amount"] < 0 and b.get("type") == "payable") or (trx["amount"] > 0 and b.get("type") == "receivable"):
                score = calculate_match_confidence(
                    trx_amount=trx["amount"],
                    trx_date=trx["transaction_date"],
                    trx_memo=trx.get("memo", ""),
                    bill_amount=b["final_amount"],
                    bill_due_date=b["due_date"],
                    bill_counterparty=b.get("counterparty_name", "")
                )
                if score > best_score:
                    best_score = score
                    best_candidate = b

        category = "divergent"
        if best_score >= 95:
            category = "safe_match"
        elif best_score >= 70:
            category = "probable_match"

        suggestions.append({
            "transaction_id": trx["id"],
            "fitid": trx["fitid"],
            "amount": float(trx["amount"]),
            "transaction_date": trx["transaction_date"].isoformat(),
            "memo": trx["memo"],
            "best_match_bill_id": best_candidate["id"] if best_candidate else None,
            "bill_title": best_candidate.get("counterparty_name") if best_candidate else None,
            "confidence_score": best_score,
            "match_category": category
        })

    return suggestions
