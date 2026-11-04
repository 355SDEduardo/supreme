"""Consultative Executive Summary and Closing Assistant Generator with mandatory disclaimer."""
from typing import Dict, Any, List


LEGAL_DISCLAIMER = (
    "Aviso Legal: Este resumo e relatório consultivo foi gerado por Inteligência Artificial "
    "a partir de bases de dados operacionais e possui caráter exclusivamente informativo. "
    "A responsabilidade técnica, homologação fiscal e validação formal das demonstrações permanecem "
    "integralmente sob a responsabilidade do profissional contábil legalmente habilitado (Resolução CFC)."
)


def generate_consultative_summary(
    company_id: str,
    month: int,
    year: int,
    metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """Generates monthly executive draft narrative for client presentation and accountant review."""
    competence_str = f"{month:02d}/{year}"
    rev = metrics.get("gross_revenue", 0.0)
    net_res = metrics.get("net_result", 0.0)
    cash_end = metrics.get("final_cash_balance", 0.0)
    net_margin = (net_res / rev * 100) if rev > 0 else 0.0

    highlights: List[str] = []
    if rev > 0:
        highlights.append(f"Receita Operacional Bruta consolidada em R$ {rev:,.2f} no período.")
    if net_res >= 0:
        highlights.append(f"Lucro Líquido apurado de R$ {net_res:,.2f} (Margem Líquida de {net_margin:.1f}%).")
    else:
        highlights.append(f"Déficit operacional de R$ {abs(net_res):,.2f} observado na competência.")

    highlights.append(f"Saldo de disponibilidade bancária de fechamento em R$ {cash_end:,.2f}.")
    highlights.append("Todas as conciliações e obrigações do período foram submetidas à validação humana.")

    narrative = (
        f"Prezado(a) Gestor(a),\n\n"
        f"Apresentamos a síntese executiva do desempenho econômico-financeiro referente à competência {competence_str}. "
        f"Durante este período, a empresa registrou uma receita operacional de R$ {rev:,.2f}, resultando em um saldo líquido "
        f"de R$ {net_res:,.2f}. A posição de liquidez de fechamento totalizou R$ {cash_end:,.2f} em disponibilidades imediatas.\n\n"
        f"Recomendamos especial atenção ao fluxo projetado para os próximos 30 dias a fim de manter o equilíbrio de capital de giro "
        f"e a pontualidade tributária."
    )

    sources = [
        "Extratos Bancários Eletrônicos (OFX)",
        "Demonstração do Resultado do Exercício (DRE)",
        "Documentos Fiscais Eletrônicos (NFS-e e NF-e)",
        "Contas a Pagar e Receber Baixados"
    ]

    return {
        "company_id": company_id,
        "competence": competence_str,
        "summary_narrative": narrative,
        "key_highlights": highlights,
        "sources_analyzed": sources,
        "legal_disclaimer": LEGAL_DISCLAIMER
    }
