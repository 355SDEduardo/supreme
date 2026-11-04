"""Consulta de retenções por competência, sem alterar as notas armazenadas."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models import NFSNacionalModel


ZERO = Decimal("0.00")
TAX_FIELDS = ("iss", "inss", "pis", "cofins", "irrf", "csll")
TOTAL_FIELDS = (*TAX_FIELDS, "total_declarado", "total_identificado", "diferenca")


def get_retention_amounts(note: NFSNacionalModel) -> Dict[str, Decimal]:
    """Discrimina os tributos retidos com as regras já usadas pela auditoria."""
    federal = note.tributos_federais
    pis_cofins_retidos = federal.tp_retencao_pis_cofins in (1, 2)
    return {
        "iss": note.valor_issqn if note.tipo_retencao_issqn == 2 else ZERO,
        "inss": federal.valor_ret_cp_inss,
        "pis": federal.valor_pis if pis_cofins_retidos else ZERO,
        "cofins": federal.valor_cofins if pis_cofins_retidos else ZERO,
        "irrf": federal.valor_ret_irrf,
        "csll": federal.valor_ret_csll,
    }


def build_retention_report(
    notes: List[NFSNacionalModel], competencia: Optional[str] = None,
) -> Dict[str, Any]:
    """Agrupa valores usando as mesmas regras da auditoria do parser.

    ISS é retido quando tipo_retencao_issqn == 2; PIS/COFINS seguem os
    indicadores 1 e 2 já utilizados pelo sistema. Valores monetários são
    somados com Decimal e enviados como strings com duas casas decimais.
    """
    competencias = sorted({n.data_competencia.isoformat()[:7] for n in notes}, reverse=True)
    selected = [n for n in notes if not competencia or n.data_competencia.isoformat()[:7] == competencia]
    selected.sort(key=lambda n: (n.data_competencia, n.numero_nfse, n.chave_nfse), reverse=True)
    totals = dict.fromkeys(TOTAL_FIELDS, ZERO)
    rows = []

    for note in selected:
        amounts = get_retention_amounts(note)
        # Incluir notas com tributos identificados mesmo se vTotalRet estiver ausente.
        if note.valor_total_retencoes == ZERO and all(value == ZERO for value in amounts.values()):
            continue

        amounts["total_declarado"] = note.valor_total_retencoes
        amounts["total_identificado"] = sum((amounts[field] for field in TAX_FIELDS), ZERO)
        amounts["diferenca"] = amounts["total_declarado"] - amounts["total_identificado"]
        for field, value in amounts.items():
            totals[field] += value

        rows.append({
            "chave_nfse": note.chave_nfse,
            "numero_nfse": note.numero_nfse,
            "competencia": note.data_competencia.isoformat()[:7],
            "tomador": note.tomador.razao_social or note.tomador.cnpj or note.tomador.cpf or "Não informado",
            **{field: format(value, ".2f") for field, value in amounts.items()},
        })

    return {
        "competencia": competencia,
        "competencias": competencias,
        "total_notas_periodo": len(selected),
        "total_notas_retencao": len(rows),
        "totais": {field: format(value, ".2f") for field, value in totals.items()},
        "notas": rows,
    }
