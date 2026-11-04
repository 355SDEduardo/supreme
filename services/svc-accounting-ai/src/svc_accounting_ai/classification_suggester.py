"""Human-in-the-loop Chart of Accounts classification suggester."""
from typing import Dict, Any, Optional

DEFAULT_ACCOUNT_RULES = [
    ("enel", "3.1.02.01", "Despesa com Energia Elétrica", "1.1.01.02", "Banco Conta Movimento", "ADM", 96.0),
    ("sabesp", "3.1.02.02", "Despesa com Água e Esgoto", "1.1.01.02", "Banco Conta Movimento", "ADM", 95.0),
    ("vivo", "3.1.02.03", "Despesa com Telecomunicações e Internet", "1.1.01.02", "Banco Conta Movimento", "ADM", 94.0),
    ("claro", "3.1.02.03", "Despesa com Telecomunicações e Internet", "1.1.01.02", "Banco Conta Movimento", "ADM", 94.0),
    ("tarifa", "3.1.04.01", "Despesas Bancárias e Tarifas", "1.1.01.02", "Banco Conta Movimento", "FIN", 98.0),
    ("aluguel", "3.1.01.05", "Despesa com Aluguéis e Condomínio", "1.1.01.02", "Banco Conta Movimento", "ADM", 92.0),
]

# In-memory learned feedback rules (Overrides defaults)
_learned_feedback_rules: Dict[str, Dict[str, Any]] = {}


def register_user_feedback(
    company_id: str,
    counterparty_keyword: str,
    debit_account: str,
    credit_account: str,
    cost_center: str
) -> None:
    """Stores human feedback with top priority over probabilistic heuristics."""
    key = f"{company_id}:{counterparty_keyword.lower()}"
    _learned_feedback_rules[key] = {
        "debit": debit_account,
        "credit": credit_account,
        "cost_center": cost_center,
        "confidence": 99.0
    }


def suggest_accounting_classification(
    company_id: str,
    description_or_memo: str,
    amount: float
) -> Dict[str, Any]:
    """Suggests debit/credit accounting entries with confidence score. Human-in-the-Loop strictly required."""
    text_lower = description_or_memo.lower()

    # 1. Check learned feedback overrides
    for key, rule in _learned_feedback_rules.items():
        comp, keyword = key.split(":", 1)
        if comp == company_id and keyword in text_lower:
            return {
                "suggested_debit_account": rule["debit"],
                "suggested_credit_account": rule["credit"],
                "suggested_cost_center": rule["cost_center"],
                "suggested_narrative": f"Pgto {description_or_memo} conf. histórico aprovado",
                "confidence_score": rule["confidence"],
                "is_learned_rule": True
            }

    # 2. Pattern matching against standard heuristics
    for kw, debit, desc, credit, cred_desc, cc, conf in DEFAULT_ACCOUNT_RULES:
        if kw in text_lower:
            return {
                "suggested_debit_account": debit,
                "suggested_credit_account": credit,
                "suggested_cost_center": cc,
                "suggested_narrative": f"Pgto {description_or_memo} conf. documento",
                "confidence_score": conf,
                "is_learned_rule": False
            }

    # 3. Fallback generic classification
    return {
        "suggested_debit_account": "3.1.09.99",
        "suggested_credit_account": "1.1.01.02",
        "suggested_cost_center": "GERAL",
        "suggested_narrative": f"Lançamento a classificar: {description_or_memo}",
        "confidence_score": 60.0,
        "is_learned_rule": False
    }
