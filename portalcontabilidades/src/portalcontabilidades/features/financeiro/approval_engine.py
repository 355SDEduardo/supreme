"""Tiered approval matrix and Segregation of Duties (Duties Segregation)."""
from decimal import Decimal
from typing import Tuple


def determine_required_approvals(amount: Decimal) -> int:
    """Calculates number of approval levels required based on bill amount."""
    if amount <= Decimal("2000.00"):
        return 1
    elif amount <= Decimal("50000.00"):
        return 2
    else:
        return 3  # Board / Executive level


def can_user_approve_bill(
    user_id: str,
    user_role: str,
    bill_creator_id: str,
    current_level: int
) -> Tuple[bool, str]:
    """Enforces Segregation of Duties: BPO preparer cannot self-approve payables."""
    # 1. BPO Preparer self-approval block
    if user_id == bill_creator_id and user_role in ("bpo_operator", "analyst"):
        return False, "Segregação de funções: o operador que cadastrou o título não pode aprová-lo."

    # 2. Check client authorization roles
    if user_role not in ("client_admin", "super_admin", "supervisor"):
        return False, f"Papel '{user_role}' não tem alçada para aprovação financeira."

    return True, "Aprovador qualificado."
