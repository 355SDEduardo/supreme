"""Shared tax-ID helpers retain formatted-input and check-digit behavior."""
import pytest

from portalcontabilidades.core.tax_ids import validate_cnpj, validate_cpf


@pytest.mark.parametrize("value, expected", [
    ("52998224725", True),
    ("529.982.247-25", True),
    ("52998224720", False),
    ("00000000000", False),
    ("", False),
    (None, False),
])
def test_validate_cpf(value, expected):
    assert validate_cpf(value) is expected


@pytest.mark.parametrize("value, expected", [
    ("11222333000181", True),
    ("11.222.333/0001-81", True),
    ("11222333000182", False),
    ("00000000000000", False),
    ("", False),
    (None, False),
])
def test_validate_cnpj(value, expected):
    assert validate_cnpj(value) is expected
