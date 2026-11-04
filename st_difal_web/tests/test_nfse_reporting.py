import csv
import json
from dataclasses import replace
from io import StringIO

from openpyxl import load_workbook

from core.nfse_pipeline import process_nfse_batch
from core.nfse_reporting import build_nfse_json_payload, generate_nfse_excel_report, generate_nfse_csv_notes, generate_nfse_csv_findings
from tests.nfse_samples import KEY, national


def test_excel_sheets_formats_provenance_and_text_identifiers():
    state = process_nfse_batch([('a.xml', national(rtc=True))])
    wb = load_workbook(generate_nfse_excel_report(state))
    assert wb.sheetnames[:6] == ['Resumo Executivo', 'Notas Auditadas', 'Apontamentos Fiscais',
        'Retenções Tributárias', 'Reforma Tributária (IBS-CBS)', 'Trilha de Proveniência']
    for ws in wb:
        assert ws.freeze_panes == 'A2'
        assert ws.auto_filter.ref
    notes = wb['Notas Auditadas']
    assert notes['B2'].value == KEY and notes['B2'].number_format == '@'
    assert notes['C2'].value == '000123'
    assert notes['P2'].number_format == '"R$" #,##0.00'
    assert notes['S2'].value == .05 and notes['S2'].number_format == '0.00%'
    assert wb['Trilha de Proveniência'].max_row > 10


def test_csv_bom_semicolons_and_json_precision_without_original_bytes():
    state = process_nfse_batch([('nota.xml', national())])
    content = generate_nfse_csv_notes(state).encode('utf-8')
    assert content.startswith(b'\xef\xbb\xbf') and b';' in content
    assert generate_nfse_csv_findings(state).startswith('\ufeff')
    payload = build_nfse_json_payload(state)
    json.dumps(payload)
    assert payload['documents'][0]['amounts']['gross_service'] == '10000.00'
    assert 'original_artifacts' not in payload
    assert len(state.original_artifacts) == 1


def test_excel_and_csv_neutralize_formula_injection():
    state = process_nfse_batch([('a.xml', national())])
    state.documents[0] = replace(state.documents[0], provider=replace(state.documents[0].provider,
        name='=HYPERLINK("https://invalid.example")'))
    ws = load_workbook(generate_nfse_excel_report(state))['Notas Auditadas']
    assert ws['J2'].data_type == 's'
    csv_rows = list(csv.reader(StringIO(generate_nfse_csv_notes(state)), delimiter=';'))
    assert csv_rows[1][9].startswith("'=")
