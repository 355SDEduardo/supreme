"""Aging List calculation and financial penalties (multa & juros pro-rata)."""
from datetime import date
from decimal import Decimal
from typing import Dict, Any, List, Tuple


def calculate_late_penalties(
    original_amount: Decimal,
    due_date: date,
    calculation_date: date,
    penalty_rate_pct: Decimal = Decimal("2.0"),  # 2% fixed penalty
    monthly_interest_rate_pct: Decimal = Decimal("1.0")  # 1% per month pro-rata
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculates late fine, pro-rata interest, and final updated amount.
    Returns: (penalty_amount, interest_amount, updated_total).
    """
    days_overdue = (calculation_date - due_date).days
    if days_overdue <= 0:
        return Decimal("0.00"), Decimal("0.00"), original_amount

    # Fixed fine (multa)
    penalty = (original_amount * penalty_rate_pct) / Decimal("100")

    # Pro-rata interest per day: (1% / 30) * days_overdue
    daily_rate = (monthly_interest_rate_pct / Decimal("100")) / Decimal("30")
    interest = original_amount * daily_rate * Decimal(days_overdue)

    updated_total = original_amount + penalty + interest
    return penalty.quantize(Decimal("0.01")), interest.quantize(Decimal("0.01")), updated_total.quantize(Decimal("0.01"))


def calculate_aging_list(bills: List[Dict[str, Any]], reference_date: date) -> Dict[str, Any]:
    """Categorizes bills into aging brackets and computes default rate (inadimplência)."""
    to_expire_1_30 = Decimal("0.00")
    to_expire_31_60 = Decimal("0.00")
    to_expire_gt_60 = Decimal("0.00")

    overdue_1_30 = Decimal("0.00")
    overdue_31_60 = Decimal("0.00")
    overdue_61_90 = Decimal("0.00")
    overdue_gt_90 = Decimal("0.00")

    total_amount = Decimal("0.00")
    total_overdue = Decimal("0.00")

    for b in bills:
        amount = Decimal(str(b["final_amount"]))
        due = b["due_date"]
        total_amount += amount
        diff_days = (due - reference_date).days

        if diff_days >= 0:
            # A Vencer
            if diff_days <= 30:
                to_expire_1_30 += amount
            elif diff_days <= 60:
                to_expire_31_60 += amount
            else:
                to_expire_gt_60 += amount
        else:
            # Vencido
            days_late = abs(diff_days)
            total_overdue += amount
            if days_late <= 30:
                overdue_1_30 += amount
            elif days_late <= 60:
                overdue_31_60 += amount
            elif days_late <= 90:
                overdue_61_90 += amount
            else:
                overdue_gt_90 += amount

    default_rate = float((total_overdue / total_amount * Decimal("100")).quantize(Decimal("0.01"))) if total_amount > 0 else 0.0

    return {
        "reference_date": reference_date.isoformat(),
        "total_receivables": float(total_amount),
        "total_overdue": float(total_overdue),
        "default_rate_pct": default_rate,
        "to_expire": {
            "1_to_30_days": float(to_expire_1_30),
            "31_to_60_days": float(to_expire_31_60),
            "greater_than_60_days": float(to_expire_gt_60),
        },
        "overdue": {
            "1_to_30_days": float(overdue_1_30),
            "31_to_60_days": float(overdue_31_60),
            "61_to_90_days": float(overdue_61_90),
            "greater_than_90_days": float(overdue_gt_90),
        }
    }
