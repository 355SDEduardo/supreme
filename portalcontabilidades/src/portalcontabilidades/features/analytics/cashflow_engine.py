"""Cash Flow Engine: Realized vs Projected cash movements and negative balance detection."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple


def calculate_daily_cash_flow(
    initial_balance: Decimal,
    days_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Computes daily cash flow sequence and checks for negative deficit alerts.
    Formula: Opening Balance + Realized/Projected Inflows - Realized/Projected Outflows == Closing Balance.
    """
    current_balance = initial_balance
    timeline = []
    deficit_alerts = []

    for entry in days_data:
        day_date = entry["date"]
        inflows_realized = Decimal(str(entry.get("inflows_realized", 0.0)))
        inflows_projected = Decimal(str(entry.get("inflows_projected", 0.0)))
        outflows_realized = Decimal(str(entry.get("outflows_realized", 0.0)))
        outflows_projected = Decimal(str(entry.get("outflows_projected", 0.0)))

        opening_day_bal = current_balance
        total_in = inflows_realized + inflows_projected
        total_out = outflows_realized + outflows_projected

        closing_day_bal = opening_day_bal + total_in - total_out
        current_balance = closing_day_bal

        is_negative = closing_day_bal < Decimal("0.00")
        if is_negative:
            deficit_alerts.append({
                "date": day_date.isoformat() if isinstance(day_date, date) else str(day_date),
                "deficit_amount": float(abs(closing_day_bal)),
                "message": f"Alerta de Caixa Negativo: saldo projetado em déficit de R$ {abs(closing_day_bal):,.2f} em {day_date}."
            })

        timeline.append({
            "date": day_date.isoformat() if isinstance(day_date, date) else str(day_date),
            "opening_balance": float(opening_day_bal),
            "inflows_total": float(total_in),
            "outflows_total": float(total_out),
            "closing_balance": float(closing_day_bal),
            "is_negative": is_negative
        })

    return {
        "initial_balance": float(initial_balance),
        "final_projected_balance": float(current_balance),
        "has_negative_balance_alert": len(deficit_alerts) > 0,
        "deficit_alerts": deficit_alerts,
        "timeline": timeline
    }
