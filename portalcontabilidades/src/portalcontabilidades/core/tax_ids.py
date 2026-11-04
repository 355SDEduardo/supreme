"""Validation and sanitization of Brazilian CNPJ and CPF."""
import re
from typing import Tuple


def clean_tax_id(tax_id: str) -> str:
    """Removes dots, slashes, dashes and whitespace."""
    if not tax_id:
        return ""
    return re.sub(r"\D", "", tax_id)


def validate_cnpj(cnpj: str) -> bool:
    """Validates a 14-digit Brazilian CNPJ using modulo 11 algorithm."""
    cleaned = clean_tax_id(cnpj)
    if len(cleaned) != 14:
        return False

    # Check for known dummy patterns (all same digits)
    if len(set(cleaned)) == 1:
        return False

    # First check digit
    weights_first = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum_first = sum(int(digit) * weight for digit, weight in zip(cleaned[:12], weights_first))
    remainder_first = sum_first % 11
    dv1 = 0 if remainder_first < 2 else 11 - remainder_first

    if int(cleaned[12]) != dv1:
        return False

    # Second check digit
    weights_second = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum_second = sum(int(digit) * weight for digit, weight in zip(cleaned[:13], weights_second))
    remainder_second = sum_second % 11
    dv2 = 0 if remainder_second < 2 else 11 - remainder_second

    return int(cleaned[13]) == dv2


def validate_cpf(cpf: str) -> bool:
    """Validates an 11-digit Brazilian CPF using modulo 11 algorithm."""
    cleaned = clean_tax_id(cpf)
    if len(cleaned) != 11:
        return False

    if len(set(cleaned)) == 1:
        return False

    # First check digit
    sum_first = sum(int(digit) * (10 - i) for i, digit in enumerate(cleaned[:9]))
    remainder_first = sum_first % 11
    dv1 = 0 if remainder_first < 2 else 11 - remainder_first

    if int(cleaned[9]) != dv1:
        return False

    # Second check digit
    sum_second = sum(int(digit) * (11 - i) for i, digit in enumerate(cleaned[:10]))
    remainder_second = sum_second % 11
    dv2 = 0 if remainder_second < 2 else 11 - remainder_second

    return int(cleaned[10]) == dv2


def validate_tax_id(tax_id: str) -> Tuple[bool, str]:
    """Validates either CNPJ or CPF and returns type."""
    cleaned = clean_tax_id(tax_id)
    if len(cleaned) == 14:
        if validate_cnpj(cleaned):
            return True, "CNPJ"
        return False, "CNPJ inválido"
    elif len(cleaned) == 11:
        if validate_cpf(cleaned):
            return True, "CPF"
        return False, "CPF inválido"
    return False, "Formato inválido (deve conter 11 dígitos para CPF ou 14 dígitos para CNPJ)"


def format_cnpj(cnpj: str) -> str:
    cleaned = clean_tax_id(cnpj)
    if len(cleaned) != 14:
        return cnpj
    return f"{cleaned[:2]}.{cleaned[2:5]}.{cleaned[5:8]}/{cleaned[8:12]}-{cleaned[12:]}"


def format_cpf(cpf: str) -> str:
    cleaned = clean_tax_id(cpf)
    if len(cleaned) != 11:
        return cpf
    return f"{cleaned[:3]}.{cleaned[3:6]}.{cleaned[6:9]}-{cleaned[9:]}"
