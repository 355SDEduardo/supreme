"""Decimal accounting helpers; never perform monetary arithmetic in binary floats."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal('0.01')

def parse_br_number(value) -> Decimal:
    if value is None or str(value).strip() in {'', '-', '—'}:
        return Decimal('0')
    text = str(value).strip().replace('R$', '').replace('%', '').replace(' ', '').replace('\u00a0', '')
    negative = text.startswith('(') and text.endswith(')')
    text = text.strip('()')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('Valor monetário inválido.') from exc
    if not result.is_finite():
        raise ValueError('Valor monetário não finito.')
    return -result if negative else result

def money(value) -> Decimal:
    return parse_br_number(value).quantize(CENT, rounding=ROUND_HALF_UP)

def format_brl(value) -> str:
    return 'R$ ' + f'{money(value):,.2f}'.translate(str.maketrans(',.', '.,'))
