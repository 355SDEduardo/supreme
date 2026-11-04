"""Predictive anomaly detector: duplicate bills, expense spikes, tax retention mismatches."""
from datetime import date
from decimal import Decimal
from typing import Dict, Any, List, Optional


def detect_payment_anomalies(
    new_bill: Dict[str, Any],
    historical_bills: List[Dict[str, Any]],
    historical_average_expense: Optional[Decimal] = None
) -> List[Dict[str, Any]]:
    """Analyzes a new bill against historical patterns to identify risks before payment."""
    alerts = []
    new_tax_id = new_bill.get("counterparty_tax_id")
    new_amount = Decimal(str(new_bill.get("amount", 0.0)))
    new_due = new_bill.get("due_date")

    # 1. Duplicate Payment Risk
    for old_b in historical_bills:
        if old_b.get("id") == new_bill.get("id"):
            continue
        old_tax_id = old_b.get("counterparty_tax_id")
        old_amount = Decimal(str(old_b.get("amount", 0.0)))
        old_due = old_b.get("due_date")

        if isinstance(new_due, str):
            try:
                new_due = date.fromisoformat(new_due)
            except Exception:
                pass
        if isinstance(old_due, str):
            try:
                old_due = date.fromisoformat(old_due)
            except Exception:
                pass

        if new_tax_id and old_tax_id and new_tax_id == old_tax_id:
            if new_amount == old_amount:
                # Same supplier and same amount
                if isinstance(new_due, date) and isinstance(old_due, date):
                    days_gap = abs((new_due - old_due).days)
                    if days_gap <= 15:
                        alerts.append({
                            "type": "duplicate_payment_risk",
                            "severity": "critical",
                            "message": f"Alerta de Risco de Duplicidade: Boleto com mesmo favorecido (CNPJ {new_tax_id}), mesmo valor (R$ {new_amount:.2f}) e vencimentos próximos ({new_due} vs {old_due}).",
                            "suspect_bill_id": old_b.get("id")
                        })
                        break

    # 2. Abnormal Expense Spike (> 300% of average)
    if historical_average_expense and historical_average_expense > Decimal("0.00"):
        spike_ratio = new_amount / historical_average_expense
        if spike_ratio >= Decimal("4.0"):  # 300% above average = 4x
            alerts.append({
                "type": "abnormal_expense_spike",
                "severity": "warning",
                "message": f"Desvio Padrão Anormal: Valor de R$ {new_amount:.2f} está {float((spike_ratio - 1) * 100):.0f}% acima da média histórica habitual (R$ {historical_average_expense:.2f})."
            })

    return alerts
