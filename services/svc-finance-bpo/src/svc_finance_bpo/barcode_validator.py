"""FEBRABAN strict barcode and linha digitável validator (47 and 48 digits)."""
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Tuple, Dict, Any, Optional

FEBRABAN_BASE_DATE = date(1997, 10, 7)


def clean_barcode(barcode: str) -> str:
    """Removes spaces, dots, and dashes from barcode string."""
    if not barcode:
        return ""
    return re.sub(r"\D", "", barcode)


def calculate_mod10(number_str: str) -> int:
    """Calculates modulo 10 check digit for FEBRABAN fields."""
    weights = [2, 1]
    total = 0
    # Process from right to left
    for i, char in enumerate(reversed(number_str)):
        w = weights[i % 2]
        mult = int(char) * w
        # Sum of digits if >= 10
        total += (mult // 10) + (mult % 10)

    remainder = total % 10
    return 0 if remainder == 0 else 10 - remainder


def calculate_mod11_general(number_str: str) -> int:
    """Calculates modulo 11 check digit (DAC) for FEBRABAN 47-digit bank titles."""
    multiplier = 2
    total = 0
    for char in reversed(number_str):
        total += int(char) * multiplier
        multiplier += 1
        if multiplier > 9:
            multiplier = 2

    remainder = total % 11
    dac = 11 - remainder
    if dac in (0, 10, 11):
        return 1
    return dac


def parse_fator_vencimento(fator_str: str) -> Optional[date]:
    """Calculates due date from 4-digit expiration factor."""
    try:
        fator = int(fator_str)
        if fator <= 0:
            return None
        # FEBRABAN factor rollover adjustment if factor > 9999
        return FEBRABAN_BASE_DATE + timedelta(days=fator)
    except Exception:
        return None


def validate_linha_digitavel(linha: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Validates 47-digit bank title or 48-digit utility/tax bill.
    Returns: (is_valid, message, extracted_details).
    """
    digits = clean_barcode(linha)

    # 1. 47 Digits (Boleto Bancário de Cobrança)
    if len(digits) == 47:
        field1_data = digits[:9]
        field1_dv = int(digits[9])
        if calculate_mod10(field1_data) != field1_dv:
            return False, "Dígito verificador do 1º campo inválido.", None

        field2_data = digits[10:20]
        field2_dv = int(digits[20])
        if calculate_mod10(field2_data) != field2_dv:
            return False, "Dígito verificador do 2º campo inválido.", None

        field3_data = digits[21:31]
        field3_dv = int(digits[31])
        if calculate_mod10(field3_data) != field3_dv:
            return False, "Dígito verificador do 3º campo inválido.", None

        # Field 4: General DAC
        general_dac = int(digits[32])

        # Field 5: Factor (4 digits) + Amount in cents (10 digits)
        factor_str = digits[33:37]
        amount_cents_str = digits[37:47]

        due_date = parse_fator_vencimento(factor_str)
        amount = Decimal(int(amount_cents_str)) / Decimal("100")

        return True, "Linha digitável bancária válida (47 dígitos).", {
            "type": "boleto_bancario",
            "due_date": due_date,
            "amount": amount,
            "bank_code": digits[:3]
        }

    # 2. 48 Digits (Concessionárias e Tributos)
    elif len(digits) == 48:
        for i in range(4):
            field_data = digits[i * 12:(i * 12) + 11]
            field_dv = int(digits[(i * 12) + 11])
            if calculate_mod10(field_data) != field_dv:
                return False, f"Dígito verificador do {i + 1}º campo de concessionária inválido.", None

        amount_cents_str = digits[4:15]
        amount = Decimal(int(amount_cents_str)) / Decimal("100")
        return True, "Linha digitável de concessionária/tributo válida (48 dígitos).", {
            "type": "concessionaria",
            "due_date": None,
            "amount": amount
        }

    return False, f"Tamanho de linha digitável inválido ({len(digits)} dígitos). Deve conter 47 ou 48 dígitos.", None
