"""Validation of structured category forms and SLA calculation."""
from portalcontabilidades.core.tax_ids import validate_cpf as _validate_cpf_checksum
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple, Optional


def validate_structured_ticket_data(category: str, data: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validates mandatory structured form fields per category before ticket creation (DoD)."""
    if not data:
        data = {}

    cat = category.lower()

    if cat == "admission":
        # Required: employee_name, cpf, position, salary, start_date
        required = ["employee_name", "cpf", "position", "salary", "start_date"]
        for field in required:
            if field not in data or not str(data[field]).strip():
                return False, f"Campo obrigatório ausente para Admissão: '{field}'."

        if not _validate_cpf_checksum(str(data["cpf"])):
            return False, "CPF do novo colaborador inválido."

        try:
            salary = float(data["salary"])
            if salary <= 0:
                return False, "Salário de admissão deve ser maior que zero."
        except ValueError:
            return False, "Valor de salário inválido."

    elif cat == "termination":
        required = ["employee_name", "termination_type", "notice_date"]
        for field in required:
            if field not in data or not str(data[field]).strip():
                return False, f"Campo obrigatório ausente para Rescisão: '{field}'."

    elif cat == "vacation":
        required = ["employee_name", "start_date", "days_count"]
        for field in required:
            if field not in data:
                return False, f"Campo obrigatório ausente para Férias: '{field}'."
        try:
            days = int(data["days_count"])
            if days < 5 or days > 30:
                return False, "Período de férias deve ser entre 5 e 30 dias (CLT)."
        except ValueError:
            return False, "Quantidade de dias de férias inválida."

    return True, None


def calculate_ticket_sla(priority: str) -> Tuple[int, datetime]:
    """Calculates SLA duration in business/calendar hours and due timestamp."""
    hours_map = {
        "urgent": 4,
        "high": 8,
        "medium": 24,
        "low": 48
    }
    sla_h = hours_map.get(priority.lower(), 24)
    due_at = datetime.now(timezone.utc) + timedelta(hours=sla_h)
    return sla_h, due_at
