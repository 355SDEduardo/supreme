from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
import pytest
from supreme_common.monetary import money, parse_br_number, format_brl
from supreme_common.competence import normalize_competencia
from supreme_common.security_xml import parse_safe_xml, xml_inputs
from supreme_common.spreadsheet import safe_cell
from supreme_common.tax_ids import validate_cnpj, validate_cpf
from supreme_common.auth_context import create_access_token, decode_access_token

def test_financial_precision_and_input_rejection():
    assert parse_br_number('R$ 1.234,56') == Decimal('1234.56')
    assert money('0.005') == Decimal('0.01')
    assert format_brl('1234.56') == 'R$ 1.234,56'
    for value in ('NaN','Infinity','abc'):
        with pytest.raises(ValueError):
            money(value)

@pytest.mark.parametrize('value', ['2026-10','10/2026','2026-10-12T10:00:00'])
def test_competence(value):
    assert normalize_competencia(value) == '2026-10'

def test_tax_ids():
    assert validate_cnpj('11222333000181')
    assert validate_cpf('52998224725')
    assert not validate_cnpj('11111111111111')

@pytest.mark.parametrize('payload', [b'<!DOCTYPE root [<!ENTITY x "y">]><root>&x;</root>',
    ('<!DOCTYPE r><r/>').encode('utf-16'), ('<x>'*51+'</x>'*51).encode()])
def test_hostile_xml(payload):
    with pytest.raises(ValueError):
        parse_safe_xml(payload)

def test_zip_traversal_and_bounded_ingestion():
    buffer = BytesIO()
    with ZipFile(buffer,'w') as archive:
        archive.writestr('../outside.xml', '<r/>')
    with pytest.raises(ValueError):
        xml_inputs('lote.zip',buffer.getvalue())

def test_formula_strings_and_numeric_values():
    assert safe_cell('  =HYPERLINK("x")').startswith("'")
    assert safe_cell(-100) == -100

def test_jwt_signature_algorithm_and_required_claims():
    token = create_access_token({'sub':'user','organization_id':'org','company_id':'company'})
    assert decode_access_token(token)['company_id'] == 'company'
    assert decode_access_token(token + 'broken') is None
    assert decode_access_token(create_access_token({'sub':'user'})) is None
