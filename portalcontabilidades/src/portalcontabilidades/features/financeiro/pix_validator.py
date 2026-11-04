"""PIX key and EMV payload validator."""
from portalcontabilidades.core.tax_ids import (
    validate_cnpj as _validate_cnpj_checksum,
    validate_cpf as _validate_cpf_checksum,
)
import re
import uuid
from typing import Tuple

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
PHONE_E164_REGEX = re.compile(r"^\+[1-9]\d{10,14}$")
UUID_V4_REGEX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def validate_pix_key(pix_key: str) -> Tuple[bool, str, str]:
    """Validates PIX key and returns (is_valid, key_type, message)."""
    if not pix_key or not pix_key.strip():
        return False, "unknown", "Chave PIX vazia."

    cleaned_key = pix_key.strip()
    digits_only = re.sub(r"\D", "", cleaned_key)

    # 1. Phone E.164 (must start with +)
    if cleaned_key.startswith("+"):
        if PHONE_E164_REGEX.match(cleaned_key):
            return True, "telefone", "Chave PIX Telefone válida (padrão E.164)."
        return False, "telefone", "Telefone inválido para chave PIX (deve seguir o formato internacional E.164, ex: +5511999998888)."

    # 2. CPF (11 digits, strictly non-phone)
    if len(digits_only) == 11 and "@" not in cleaned_key:
        if _validate_cpf_checksum(digits_only):
            return True, "cpf", "Chave PIX CPF válida."
        return False, "cpf", "CPF inválido para chave PIX."

    # 3. CNPJ (14 digits)
    if len(digits_only) == 14 and "@" not in cleaned_key:
        if _validate_cnpj_checksum(digits_only):
            return True, "cnpj", "Chave PIX CNPJ válida."
        return False, "cnpj", "CNPJ inválido para chave PIX."

    # 4. E-mail
    if "@" in cleaned_key:
        if EMAIL_REGEX.match(cleaned_key):
            return True, "email", "Chave PIX E-mail válida."
        return False, "email", "Formato de e-mail inválido para chave PIX."

    # 5. Chave Aleatória (EVP / UUID)
    if UUID_V4_REGEX.match(cleaned_key):
        return True, "aleatoria", "Chave PIX Aleatória (EVP) válida."

    return False, "unknown", "Formato de chave PIX não reconhecido (deve ser CPF, CNPJ, e-mail, telefone internacional E.164 com '+' ou UUID)."


def validate_pix_emv_payload(payload: str) -> Tuple[bool, str]:
    """Validates EMV QR Code payload (PIX Copia e Cola)."""
    if not payload:
        return False, "Payload PIX vazio."
    if payload.startswith("000201") and "br.gov.bcb.pix" in payload.lower():
        return True, "Payload EMV PIX Copia e Cola válido."
    return False, "Payload EMV PIX inválido (não contém cabeçalho 000201 ou identificador do Bacen)."
