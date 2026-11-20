from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest


CSV = b'data,conta_debito,conta_credito,descricao,valor\n01/01/2026,Banco,Receita,Saldo do dia,999.00\n02/01/2026,Despesa,Banco,Pix fornecedor completo,12.34\n'
OFX = b'''OFXHEADER:100
<OFX><BANKACCTFROM><BANKID>033<ACCTID>1234000000123</BANKACCTFROM>
<BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260102120000[-3:GMT]
<TRNAMT>-12,34<FITID>unique-1<MEMO>PIX FORNECEDOR</STMTTRN></BANKTRANLIST></OFX>'''


def parse(name: str, data: bytes):
    from svc_finance_bpo.statement_parsers import parse_statement

    return parse_statement(name, data, date(2026, 1, 1), date(2026, 1, 31))


def test_csv_accounting_columns_and_balance_exclusion():
    result = parse('statement.csv', CSV)
    assert len(result.rows) == 1 and result.excluded_balances == 1
    row = result.rows[0]
    assert row.date == date(2026, 1, 2) and row.amount == Decimal('12.34') and row.type == 'saida'


def test_santander_sgml_decimal_comma():
    result = parse('statement.ofx', OFX)
    assert result.bank_code == '033' and result.agency == '1234' and result.account == '123'
    row = result.rows[0]
    assert row.type == 'saida' and row.amount == Decimal('12.34') and row.reference == 'unique-1'


def test_xlsx_header_after_account_metadata():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(['AGENCIA', '1234', 'CONTA', '000000123'])
    sheet.append(['Data', 'Histórico', 'Documento', 'Valor (R$)', 'Saldo (R$)'])
    sheet.append([date(2026, 1, 2), 'Pix empresa completa', 'doc-1', -12.34, 100])
    output = BytesIO()
    book.save(output)
    result = parse('statement.xlsx', output.getvalue())
    assert result.agency == '1234' and result.account == '123'
    assert result.rows[0].amount == Decimal('12.34') and result.rows[0].type == 'saida'


def test_four_sources_complement_without_collapsing_repeated_transactions():
    from svc_finance_bpo.statement_merge import merge_sources

    ofx = parse('statement.ofx', OFX)
    csv = parse('statement.csv', CSV)
    groups = merge_sources([ofx, csv])
    assert len(groups) == 1
    assert len(groups[0].candidates) == 2
    assert groups[0].field_sources['amount'] == ofx.rows[0].id
    repeated = OFX.replace(b'</BANKTRANLIST>', OFX.split(b'<STMTTRN>')[1].split(b'</STMTTRN>')[0].join([b'<STMTTRN>', b'</STMTTRN>']).replace(b'unique-1', b'unique-2') + b'</BANKTRANLIST>')
    assert len(merge_sources([parse('twice.ofx', repeated)])) == 2


def test_ambiguous_matches_are_not_silently_combined():
    from svc_finance_bpo.statement_merge import merge_sources

    a = parse('a.csv', b'Data,Descricao,Valor\n02/01/2026,ALFA,-12.34\n02/01/2026,BETA,-12.34\n')
    b = parse('b.csv', b'Data,Descricao,Valor\n02/01/2026,GAMA,-12.34\n02/01/2026,DELTA,-12.34\n')
    groups = merge_sources([a, b])
    assert any(group.issues for group in groups)


@pytest.mark.parametrize('name,content', [('x.exe', b'x'), ('x.pdf', b'not-pdf'), ('x.xlsx', b'not-xlsx')])
def test_invalid_files_fail_explicitly(name, content):
    from svc_finance_bpo.statement_types import StatementError
    with pytest.raises(StatementError):
        parse(name, content)
