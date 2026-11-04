"""Semantic error translator: converts cryptic government SOAP faults into actionable Portuguese instructions."""
import re
from typing import Dict, Tuple

KNOWN_FISCAL_ERRORS: Dict[str, str] = {
    "401": "O CNPJ/CPF informado no evento está com formato inconsistente ou ausente de cadastro na Receita Federal.",
    "106": "Evento fiscal duplicado: já existe declaração idêntica processada com sucesso no Fisco para esta competência.",
    "MS0015": "A competência tributária já está encerrada no Fisco. Para efetuar ajustes, transmita a reabertura do período.",
    "MS0030": "Certificado digital transmissor não possui procuração eletrônica válida vinculada ao CNPJ do contribuinte no e-CAC.",
    "MS1009": "O trabalhador informado não possui vínculo ativo ou cadastro no evento inicial S-2200.",
    "503": "Serviços da Receita Federal / SEFAZ temporariamente indisponíveis (HTTP 503). Transmissão enfileirada para retentativa automática.",
    "504": "Tempo limite de resposta do gateway governamental esgotado (Timeout). A fila reenviará o lote com chave de idempotência.",
    "FAULT": "Falha na comunicação SOAP com o Web Service do Fisco. Os dados foram preservados e o envio será reprocessado."
}


def translate_fiscal_error(raw_error_code: str, raw_error_msg: str) -> str:
    """Translates cryptic federal error codes into clear, actionable Portuguese instructions."""
    code = (raw_error_code or "").strip().upper()

    # Exact code match
    if code in KNOWN_FISCAL_ERRORS:
        return KNOWN_FISCAL_ERRORS[code]

    # Keyword inspection in raw message
    raw_lower = (raw_error_msg or "").lower()
    if "procuracao" in raw_lower or "procuração" in raw_lower:
        return "Procuração eletrônica no e-CAC inexistente ou vencida para o certificado digital utilizado."
    if "timeout" in raw_lower or "timed out" in raw_lower:
        return "Comunicação com o Fisco expirou por lentidão no servidor governamental. Enfileirado para reenvio automático."
    if "duplicidade" in raw_lower:
        return "Declaração já recebida anteriormente pelo Fisco (duplicidade detectada)."
    if "nrinsc" in raw_lower:
        return "O número de inscrição (CNPJ/CPF) informado no evento não confere com o cadastro da empresa."

    return f"Retorno do Fisco (Código {raw_error_code}): {raw_error_msg}. Verifique o cadastro societário e os parâmetros fiscais da competência."
